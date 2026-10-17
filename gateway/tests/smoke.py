"""End-to-end smoke test for the gateway. Run from the gateway/ folder:

    python tests/smoke.py

It starts two fake upstreams and the gateway, then checks the behaviours the assignment
asks for: aggregation, name collisions, timeouts, a dead upstream, disabling a server,
key revocation, credential secrecy, roles and audit attribution.
"""
import asyncio
import os
import subprocess
import sys
import tempfile
import time

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

PY = sys.executable
GW = "http://127.0.0.1:9000"
procs: list[subprocess.Popen] = []
results: list[tuple[bool, str]] = []


def check(ok: bool, label: str):
    results.append((ok, label))
    print(("PASS  " if ok else "FAIL  ") + label)


def start(args: list[str], env: dict | None = None) -> subprocess.Popen:
    p = subprocess.Popen(args, env={**os.environ, **(env or {})}, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    procs.append(p)
    return p


def wait_http(url: str, tries: int = 50):
    for _ in range(tries):
        try:
            httpx.get(url, timeout=1)
            return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError(f"{url} did not come up")


async def mcp_session_call(key: str, fn):
    async with streamablehttp_client(f"{GW}/mcp", headers={"Authorization": f"Bearer {key}"}) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            return await fn(s)


async def tools(key: str) -> list[str]:
    return await mcp_session_call(key, lambda s: _names(s))


async def _names(s):
    return sorted(t.name for t in (await s.list_tools()).tools)


async def call(key: str, name: str, args: dict):
    return await mcp_session_call(key, lambda s: s.call_tool(name, args))


def text(result) -> str:
    return " ".join(c.text for c in result.content if getattr(c, "text", None))


async def main():
    tmp = tempfile.mkdtemp()
    alpha = start([PY, "tests/fake_upstream.py", "alpha", "9101"], {"REQUIRE_TOKEN": "secret-alpha"})
    beta = start([PY, "tests/fake_upstream.py", "beta", "9102"])
    start(
        [PY, "-m", "uvicorn", "app.main:app", "--port", "9000", "--log-level", "warning"],
        {
            "DB_PATH": os.path.join(tmp, "gw.db"), "SESSION_SECRET": "test-secret",
            "ADMIN_EMAIL": "admin@test.dev", "ADMIN_PASSWORD": "admin-password-1",
            "CALL_TIMEOUT": "2", "LIST_TIMEOUT": "2", "REFRESH_INTERVAL": "3",
        },
    )
    wait_http(f"{GW}/healthz")
    wait_http("http://127.0.0.1:9102/mcp")

    c = httpx.Client(base_url=GW, timeout=15)

    # ---- login and roles ----
    r = c.post("/api/login", json={"email": "admin@test.dev", "password": "admin-password-1"})
    check(r.status_code == 200, "admin can log in")
    admin_h = {"Authorization": f"Bearer {r.json()['token']}"}
    check(c.post("/api/login", json={"email": "admin@test.dev", "password": "wrong"}).status_code == 401,
          "wrong password is rejected")

    # ---- register upstreams ----
    r = c.post("/api/servers", headers=admin_h, json={
        "slug": "alpha", "url": "http://127.0.0.1:9101/mcp", "auth_type": "bearer", "credential": "secret-alpha"})
    check(r.status_code == 201 and r.json()["status"] == "connected", "alpha (needs a bearer credential) connects")
    r = c.post("/api/servers", headers=admin_h, json={"slug": "beta", "url": "http://127.0.0.1:9102/mcp"})
    check(r.status_code == 201 and r.json()["status"] == "connected", "beta connects")
    r = c.post("/api/servers", headers=admin_h, json={
        "slug": "badauth", "url": "http://127.0.0.1:9101/mcp", "auth_type": "bearer", "credential": "wrong"})
    check(r.json()["status"] == "unreachable", f"wrong credential shows unreachable ({r.json()['status_detail'][:60]!r})")
    check(c.post("/api/servers", headers=admin_h, json={"slug": "a__b", "url": "http://x"}).status_code == 422,
          "slug containing '__' is refused")

    # ---- users and keys ----
    r = c.post("/api/users", headers=admin_h, json={"email": "userb@test.dev", "password": "member-pass-1"})
    check(r.status_code == 201 and r.json()["role"] == "member", "admin invites member B")
    b_id = r.json()["id"]
    r = c.post("/api/login", json={"email": "userb@test.dev", "password": "member-pass-1"})
    b_h = {"Authorization": f"Bearer {r.json()['token']}"}
    r = c.post("/api/keys", headers=b_h, json={"name": "cursor"})
    b_key, b_key_id = r.json()["key"], r.json()["id"]
    check(r.status_code == 201 and b_key.startswith("gw_"), "member B generates their own key")
    check(b_key not in str(c.get("/api/keys", headers=b_h).json()), "listing keys never returns the plaintext key")
    check(c.post("/api/servers", headers=b_h, json={"slug": "x", "url": "http://x"}).status_code == 403,
          "member cannot add a server")
    check(c.get("/api/users", headers=b_h).status_code == 403, "member cannot list users")
    a_key = c.post("/api/keys", headers=admin_h, json={"name": "admin-key"}).json()["key"]

    # ---- credentials never leak ----
    body = c.get("/api/servers", headers=b_h).text
    check("secret-alpha" not in body and "wrong" not in body, "upstream credentials never appear in the API")

    # ---- aggregation and collisions ----
    names = await tools(b_key)
    check("alpha__echo" in names and "beta__echo" in names, f"both 'echo' tools coexist: {[n for n in names if 'echo' in n]}")
    check(not any(n.startswith("badauth__") for n in names), "unreachable server's tools are hidden")
    r = await call(b_key, "alpha__echo", {"text": "hi"})
    check(text(r) == "alpha: hi", "alpha__echo routed to alpha")
    r = await call(b_key, "beta__echo", {"text": "hi"})
    check(text(r) == "beta: hi", "beta__echo routed to beta")
    r = await call(b_key, "alpha__explode", {})
    check(r.isError and "boom from alpha" in text(r), "upstream tool error is passed back as an error")
    r = await call(b_key, "nonsense", {})
    check(r.isError, "unknown tool name returns a clear error")

    # ---- timeout: slow tool must not break anything else ----
    t0 = time.monotonic()
    r = await call(b_key, "alpha__slow", {"seconds": 6})
    took = time.monotonic() - t0
    check(r.isError and "timed out" in text(r) and took < 4, f"slow call times out in {took:.1f}s with a clear message")
    check((await call(b_key, "beta__echo", {"text": "still ok"})).isError is False, "other server unaffected by the timeout")
    st = {s["slug"]: s["status"] for s in c.get("/api/servers", headers=admin_h).json()}
    check(st["alpha"] == "connected", "a slow tool does not mark the server unreachable")

    # ---- dead upstream ----
    beta.kill()
    beta.wait()
    r = await call(b_key, "beta__echo", {"text": "x"})
    check(r.isError and "failed" in text(r), "call to a dead upstream returns a clear error")
    check((await call(b_key, "alpha__echo", {"text": "alive"})).isError is False, "alpha keeps working while beta is dead")
    st = {s["slug"]: s["status"] for s in c.get("/api/servers", headers=admin_h).json()}
    check(st["beta"] == "unreachable", "dashboard shows the dead server as unreachable")
    names = await tools(b_key)
    check(not any(n.startswith("beta__") for n in names) and "alpha__echo" in names, "dead server's tools drop out of the list")

    # ---- disable ----
    alpha_id = next(s["id"] for s in c.get("/api/servers", headers=admin_h).json() if s["slug"] == "alpha")
    r = c.patch(f"/api/servers/{alpha_id}", headers=admin_h, json={"enabled": False})
    check(r.json()["status"] == "disabled", "disabling a server shows status disabled")
    names = await tools(b_key)
    check(not any(n.startswith("alpha__") for n in names), "disabled server's tools disappear")
    r = await call(b_key, "alpha__echo", {"text": "x"})
    check(r.isError, "calling a disabled server's tool is refused")
    c.patch(f"/api/servers/{alpha_id}", headers=admin_h, json={"enabled": True})

    # ---- revoke ----
    check(c.delete(f"/api/keys/{b_key_id}", headers=b_h).status_code == 204, "member B revokes their own key")
    rejected = False
    try:
        await call(b_key, "alpha__echo", {"text": "x"})
    except BaseException as exc:  # a 401 surfaces as an HTTP error inside the client
        rejected = True
    check(rejected, "revoked key is rejected on the next call")
    check(httpx.post(f"{GW}/mcp", headers={"Authorization": "Bearer gw_nope"}, json={}).status_code == 401,
          "unknown key gets HTTP 401")

    # ---- audit ----
    rows = c.get("/api/audit", headers=admin_h).json()
    mine = [x for x in rows if x["user_email"] == "userb@test.dev"]
    outcomes = {x["outcome"] for x in mine}
    check({"success", "error", "timeout", "rejected"} <= outcomes, f"audit has B's calls with outcomes {sorted(outcomes)}")
    check(any(x["tool"] == "echo" and x["server"] == "alpha" and x["duration_ms"] >= 0 for x in mine),
          "audit rows carry user, server, tool and duration")
    check(any(x["tool"] == "(auth)" and x["outcome"] == "rejected" for x in mine), "revoked-key attempt is audited under B")
    b_view = c.get("/api/audit", headers=b_h)
    check(b_view.status_code == 200 and all(x["user_email"] == "userb@test.dev" for x in b_view.json()),
          "a member sees only their own audit rows")

    # ---- admin key still works ----
    check("alpha__echo" in await tools(a_key), "admin's key still works after B's was revoked")


try:
    asyncio.run(main())
finally:
    for p in procs:
        if p.poll() is None:
            p.kill()
failed = [label for ok, label in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
sys.exit(1 if failed else 0)