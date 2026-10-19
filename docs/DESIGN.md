# System design and tradeoffs

## What was built

A team MCP gateway on Kubernetes. Teammates point their MCP client (Claude Code, Cursor, MCP Inspector) at **one URL and one key**. Behind it sit several upstream MCP servers: a WooCommerce server (store admin), a utilities server and a notes server. Admins manage servers, members and keys from a web dashboard, which also has a chat agent that uses the same tools.

```
 MCP client ──Bearer gw_key──┐                      ┌── mcp-woo ──► WooCommerce (store ns)
                             ├─► Traefik ─► gateway ┼── utils   (extras ns)
 Browser ─► dashboard (nginx)┘   /mcp /api   │      └── notes   (extras ns)
            chat ─► /api/chat ─► core.call_tool ─► LLM (OpenAI-compatible API)
                                     │
                                  SQLite on a PVC: users, keys, servers, audit
```

| Piece | Namespace | Job |
|---|---|---|
| store (MySQL + WordPress/WooCommerce) | store | The shop. REST API keys live in a Secret. |
| mcp-woo | store | MCP server wrapping the WooCommerce REST API. A NetworkPolicy admits only the gateway pod. |
| utils, notes | extras | Small extra upstream servers (time, arithmetic, notes) to show the gateway is generic. |
| gateway | gateway | One `/mcp` endpoint, the `/api` admin API, auth, audit, the chat agent. |
| dashboard | gateway | Static React app served by non-root nginx. Ingress path `/`. |
| Traefik | traefik | Ingress controller (ingress-nginx is retired). |

## Decisions

**One public surface, one key.** Clients never see upstream URLs or upstream credentials. The gateway holds those and uses them itself. The client's gateway key is never forwarded upstream.

**Tool names are `slug__tool`.** Slugs may contain only lowercase letters, digits and hyphens, so splitting on the first `__` always recovers the server. Two servers that both have an `echo` tool never collide, and each description is tagged `[slug]` so a tool cannot claim to be another server's.

**Listing is cached, calls are live.** A background loop asks each enabled upstream for its tools every 15 s, in parallel, and stores the result. `tools/list` reads the cache, so a slow or dead upstream cannot slow it down or break it. Calls open a short session to exactly one upstream.

**Failure isolation.** A connection error marks a server Unreachable at once and removes its tools from the list. A timeout returns a clear error but does not mark the server dead, because a slow tool is not a dead server. One upstream failing never affects the others.

**Stateless MCP over HTTP.** The gateway keeps no MCP session state, so any replica could answer any request. Only SQLite stops us scaling out.

**Auth.** Members and admins sign in with email and password (scrypt, per-user salt) and get an HMAC-signed token that lasts 12 hours. API keys are `gw_` plus 256 random bits, shown once, stored only as SHA-256. Revoking a key takes effect on the next request. Roles: admin (manage servers, members, all keys, all audit rows) and member (own keys, own audit rows, use tools).

**Audit.** Every tool call goes through one function (`core.call_tool`), from the MCP endpoint and from the chat agent alike, and writes user, server, tool, duration and outcome. Rejected attempts with a revoked key are recorded too, under the key's owner. There is no code path that calls an upstream without writing the row.

**Chat agent.** An OpenAI-compatible tool loop (Groq with `openai/gpt-oss-120b` by default; any compatible API works). It calls tools through `core.call_tool` as the logged-in user, so permissions and audit are the same as an external client. Capped at 6 steps. The system prompt tells the model that tool output is data, not instructions. Gateway credentials are never sent to the model.

**WooCommerce over HTTPS.** WooCommerce accepts key/secret Basic auth only over HTTPS. Inside the cluster the traffic is HTTP, so mcp-woo sends `X-Forwarded-Proto: https`, which the WordPress image honours. Order times are UTC, so the time tool and the order tool both work in UTC.

## Tradeoffs we accepted

| Choice | Why | What it costs | What we would do next |
|---|---|---|---|
| SQLite on one PVC, single replica (`Recreate` strategy) | Zero extra services, simple to run and demo | No high availability, a restart means a short gap | Postgres, then more replicas |
| Upstream credentials in plaintext in SQLite | The volume is private to the pod; keeps the code small | Anyone with the volume reads them | Encrypt with a key from a Secret or a KMS |
| 15 s tool-list refresh | Fast listing, cheap | A new tool can take up to 15 s to appear | Refresh on demand after an admin edit (done for add/edit), or webhooks |
| New session per upstream call | Simple, no leaked state | Slightly higher latency per call | Pooled sessions |
| Session token in `sessionStorage` | Two users can sign in in two tabs; cleared when the tab closes | Readable by any script on the page | Strict CSP is set; an httpOnly cookie would need CSRF protection |
| No rate limiting or lockout | Out of time budget | Password guessing is possible | Per-IP and per-account limits at Traefik or in the app |
| Admin may register any URL | Flexible | SSRF: an admin could point the gateway at internal addresses | Allow-list of hosts or namespaces |
| Tool arguments are passed as the model wrote them | Keeps the agent general | A confused model could change an order status | Confirmation step for write tools, per-role tool permissions |