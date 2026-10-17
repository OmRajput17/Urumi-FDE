# Team MCP Gateway (Module 3)

One MCP endpoint (`/mcp`) in front of many upstream MCP servers, plus an admin API (`/api`) for the dashboard.

## Run it locally

From the `gateway/` folder (Windows cmd):

```
uv sync
set SESSION_SECRET=dev-secret-change-me
set ADMIN_PASSWORD=admin-password-1
set DB_PATH=gateway.db
uv run uvicorn app.main:app --port 9000
```

Run the checks (starts two fake upstreams and the gateway itself, then tears them down):

```
uv run python tests/smoke.py
```

To try it against your real WooCommerce MCP server, keep `kubectl port-forward -n store svc/mcp-woo 8000:8000` running and start the gateway with `set SEED_WOO_URL=http://localhost:8000/mcp`.

## Deploy to the kind cluster

```
docker build -t gateway:0.1.0 ./gateway
kind load docker-image gateway:0.1.0 --name urumi
helm install gateway ./gateway/chart -n gateway --set admin.password=CHANGE_ME --set sessionSecret=CHANGE_ME_TOO
kubectl get pods -n gateway
```

The `gateway` namespace and the pod label `app.kubernetes.io/name=gateway` are what the MCP server's NetworkPolicy admits.
Public URLs (Traefik): `http://dashboard.localhost/api/...` and `http://dashboard.localhost/mcp`.

## How it works

**Tool names.** Every tool is exposed as `<server slug>__<tool>` (for example `alpha__echo`). Slugs may only contain lowercase letters, digits and hyphens, so splitting on the first `__` always recovers the server. Two servers with an `echo` tool never collide. Each description is also tagged `[slug]` so a tool cannot pass itself off as belonging to another server.

**Listing is instant.** A background loop asks every enabled server for its tools every 15 seconds (all at the same time, 5 second timeout each) and stores the result. `tools/list` reads that cache, so a slow or dead upstream cannot slow it down. Unreachable servers are left out of the list.

**Calls are isolated.** Each call opens its own short-lived session to the one upstream it needs, with a 30 second timeout. Timeouts and connection failures come back as clear errors. A connection failure marks the server `unreachable` immediately. A timeout does not, because a slow tool is not a dead server.

**Credentials.** Upstream credentials are stored server-side and never returned by any endpoint (only `has_credential: true`). The client's gateway key is never forwarded upstream: the gateway uses the upstream's own credential instead.

**Keys and passwords.** API keys are random 256-bit values shown once; only their SHA-256 hash is stored. Passwords use scrypt with a per-user salt.

**Audit.** Every tool call, from the MCP endpoint or the chat agent, goes through `core.call_tool`, which writes user, server, tool, time, duration and outcome. Attempts with a revoked key are audited under the key's owner.

## Known tradeoffs

- SQLite on one PVC means one gateway replica. More replicas would need Postgres. The MCP side is already stateless.
- Upstream credentials are stored in plaintext in SQLite (the volume is private to the pod). Encrypting them at rest is a listed stand-out item, not done.
- A new server is checked as soon as it is added, and every 15 seconds after, so the tool list can be up to 15 seconds stale.
- No SSRF protection yet: an admin can register any URL, including cluster-internal addresses.