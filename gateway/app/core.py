"""Gateway core: aggregate tools from upstream servers, route calls, audit everything.

The MCP endpoint (for external clients) and the chat agent both call these same
functions, which is why every call is audited under the right user no matter who made it.
"""
import asyncio
import json
import time

from . import config, db, security, upstream

# Public tool name = <server slug>__<tool name>. Slugs may not contain "__", so splitting
# on the first "__" always recovers the server. Two servers can both have an "echo" tool:
# they appear as "alpha__echo" and "beta__echo" and never collide.
SEP = "__"


class GatewayError(Exception):
    def __init__(self, message: str, outcome: str = "error"):
        super().__init__(message)
        self.outcome = outcome


def public_name(slug: str, tool: str) -> str:
    return f"{slug}{SEP}{tool}"


def split_name(name: str) -> tuple[str, str]:
    if SEP not in name:
        raise GatewayError(f"Unknown tool '{name}'. Tool names look like <server>{SEP}<tool>.")
    slug, tool = name.split(SEP, 1)
    return slug, tool


# ---------- startup seeding ----------

def seed() -> None:
    if not db.one("SELECT id FROM users LIMIT 1"):
        db.execute(
            "INSERT INTO users (email, password_hash, role, created_at) VALUES (?, ?, 'admin', ?)",
            (config.ADMIN_EMAIL.lower(), security.hash_password(config.ADMIN_PASSWORD), db.now()),
        )
    if config.SEED_WOO_URL and not db.one("SELECT id FROM servers WHERE slug = 'woocommerce'"):
        db.execute(
            "INSERT INTO servers (slug, url, auth_type, created_at) VALUES ('woocommerce', ?, 'none', ?)",
            (config.SEED_WOO_URL, db.now()),
        )


# ---------- upstream health and tool cache ----------

async def refresh_server(server_id: int) -> None:
    server = db.one("SELECT * FROM servers WHERE id = ?", (server_id,))
    if not server:
        return
    if not server["enabled"]:
        db.execute(
            "UPDATE servers SET status='disabled', status_detail=NULL, last_checked=? WHERE id=?",
            (db.now(), server_id),
        )
        return
    try:
        tools = await upstream.list_tools(server, config.LIST_TIMEOUT)
        db.execute(
            "UPDATE servers SET status='connected', status_detail=NULL, last_checked=?, tools_json=? WHERE id=?",
            (db.now(), json.dumps(tools), server_id),
        )
    except upstream.UpstreamError as exc:
        db.execute(
            "UPDATE servers SET status='unreachable', status_detail=?, last_checked=? WHERE id=?",
            (str(exc), db.now(), server_id),
        )


async def refresh_all() -> None:
    """Check every server at the same time, so one slow server never delays the others."""
    ids = [s["id"] for s in db.query("SELECT id FROM servers")]
    await asyncio.gather(*(refresh_server(i) for i in ids), return_exceptions=True)


async def refresh_loop() -> None:
    while True:
        await refresh_all()
        await asyncio.sleep(config.REFRESH_INTERVAL)


def tools_of(server: dict) -> list[dict]:
    return json.loads(server["tools_json"])


# ---------- what a client sees ----------

def list_tools_for(user: dict) -> list[dict]:
    """Tools of every enabled, reachable server, served from the cache (instant)."""
    tools = []
    for server in db.query("SELECT * FROM servers WHERE enabled = 1 AND status = 'connected' ORDER BY slug"):
        for tool in tools_of(server):
            tools.append(
                {
                    "name": public_name(server["slug"], tool["name"]),
                    # Tag the origin so a tool cannot pretend to belong to another server.
                    "description": f"[{server['slug']}] {tool['description']}".strip(),
                    "inputSchema": tool["inputSchema"],
                }
            )
    return tools


async def call_tool(user: dict, name: str, arguments: dict | None):
    """Route one call to its upstream with a timeout, and write the audit row."""
    started = time.monotonic()
    server_slug, tool, outcome, detail = "-", name, "success", None
    try:
        server_slug, tool = split_name(name)
        server = db.one("SELECT * FROM servers WHERE slug = ?", (server_slug,))
        if not server or not server["enabled"]:
            raise GatewayError(f"Server '{server_slug}' is unknown or disabled.", "rejected")
        try:
            result = await upstream.call_tool(server, tool, arguments, config.CALL_TIMEOUT)
        except upstream.UpstreamError as exc:
            timed_out = "timed out" in str(exc)
            if not timed_out:  # a slow tool is not a dead server; a refused connection is
                db.execute(
                    "UPDATE servers SET status='unreachable', status_detail=?, last_checked=? WHERE id=?",
                    (str(exc), db.now(), server["id"]),
                )
            raise GatewayError(
                f"Upstream '{server_slug}' failed: {exc}", "timeout" if timed_out else "error"
            ) from None
        if result.isError:
            outcome = "error"
            detail = next((c.text for c in result.content if getattr(c, "text", None)), "tool reported an error")
        return result
    except GatewayError as exc:
        outcome, detail = exc.outcome, str(exc)
        raise
    finally:
        db.execute(
            "INSERT INTO audit (ts, user_id, user_email, server, tool, duration_ms, outcome, detail) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                db.now(), user["id"], user["email"], server_slug, tool,
                int((time.monotonic() - started) * 1000), outcome, (detail or "")[:500],
            ),
        )


# ---------- API key authentication ----------

def authenticate_api_key(key: str) -> dict | None:
    """Return the user for a valid key. A revoked key is refused and the attempt is audited."""
    row = db.one(
        "SELECT k.id AS key_id, k.revoked_at, u.id, u.email, u.role, u.disabled "
        "FROM api_keys k JOIN users u ON u.id = k.user_id WHERE k.key_hash = ?",
        (security.hash_key(key),),
    )
    if not row:
        return None  # unknown key: nobody to attribute it to
    if row["revoked_at"] or row["disabled"]:
        reason = "revoked key" if row["revoked_at"] else "disabled user"
        db.execute(
            "INSERT INTO audit (ts, user_id, user_email, server, tool, duration_ms, outcome, detail) "
            "VALUES (?, ?, ?, '-', '(auth)', 0, 'rejected', ?)",
            (db.now(), row["id"], row["email"], f"rejected: {reason}"),
        )
        return None
    return {"id": row["id"], "email": row["email"], "role": row["role"]}