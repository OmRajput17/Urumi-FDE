# Threat model

Scope: the gateway, dashboard, chat agent and the way they reach the store. Local demo (kind) and a single-node VPS (k3s) are the intended deployments.

## What we protect

1. **Store data and actions**: orders, customers, product creation, order status changes.
2. **Credentials**: WooCommerce API key/secret, upstream bearer tokens, the LLM API key, gateway API keys, user passwords.
3. **The audit trail**: it must say truthfully who did what.

## Who might attack

- A teammate whose key leaked (laptop, chat, git).
- A member trying to do admin things or read others' data.
- A malicious or compromised upstream MCP server.
- Content in the store (a product name, an order note) that tries to steer the chat agent.
- Anyone on the network who can reach the Ingress.

## Threats and what we did

| Threat | Mitigation in place | Gap |
|---|---|---|
| Leaked gateway key | Keys are random 256-bit, stored hashed, shown once, revocable. A revoked key fails with 401 on the very next call and the attempt is audited. | Keys do not expire. No per-key scope. |
| Stolen database file | Passwords use scrypt with a salt. API keys are only hashed. | Upstream credentials are plaintext. |
| Member escalates to admin | Every admin route depends on an admin check on the server, not only a hidden button. Members see only their own keys and audit rows. | The browser test confirms a member sees no admin controls. |
| Password guessing | Strong hashing slows offline attacks. Wrong-password message does not say which part was wrong. | **No rate limiting or lockout.** |
| Stolen session token | HMAC-signed, 12 h expiry, cleared when the tab closes. Disabled users are refused on the next request. | Token readable by page scripts; CSP limits what scripts can run. |
| XSS in the dashboard | React escapes output. Chat output goes through react-markdown without raw HTML. nginx sends a strict CSP (`default-src 'self'`), `nosniff`, no-referrer, no framing. | `style-src 'unsafe-inline'` is allowed for inline styles. |
| Prompt injection through tool output | The system prompt marks tool text as data. The loop is capped at 6 steps. The agent acts only as the logged-in user and every call is audited. | The model can still be fooled into calling a write tool. No confirmation step. |
| Malicious upstream | Tool names are namespaced and descriptions tagged, so it cannot impersonate another server. Timeouts bound how long it can stall. Its tools are only visible when it is healthy. | It can still return misleading text to the model. |
| SSRF via "Add server" | Only admins can add a server and only `http(s)` URLs are accepted. | **An admin can target internal addresses.** |
| Reaching mcp-woo or the store API directly | NetworkPolicy on mcp-woo admits only the `gateway` namespace and the pod label `app.kubernetes.io/name=gateway` (both in one `from` entry, so it is AND, not OR). WooCommerce keys are in a Kubernetes Secret and are never returned by any endpoint. | Secrets are base64, not encryption. Anyone with `kubectl get secret` can read them. |
| Secrets in git | Passwords and keys are passed with `--set` at install time. `values.yaml` holds empty placeholders. | Must be checked before each push (see README). |
| LLM provider sees data | The LLM receives the user's question and tool results, never gateway credentials. | Order data (names, totals) goes to a third party. For real use, pick a provider under a data agreement or self-host. |
| Container compromise | Non-root numeric users, `runAsNonRoot`, dropped capabilities and read-only root filesystem on the dashboard, resource limits on every pod. | The gateway needs a writable volume for SQLite. |

## Before real production use

1. Rate limiting and lockout on login.
2. Encrypt upstream credentials at rest. Use sealed secrets or an external secret store.
3. TLS everywhere (cert-manager with Let's Encrypt on the VPS).
4. Allow-list for upstream URLs.
5. Confirmation or approval for write tools in the chat agent, and per-role tool permissions.
6. Key expiry and rotation.
7. Postgres and more than one replica.

## The four questions in the brief

**1. Shared upstream credentials: what can a member do with a credential they never see?**
A member cannot read it: no endpoint returns an upstream credential (servers show only `has_credential: true`), and it is never sent to a browser, a client or the chat model. But the gateway uses that credential on the member's behalf, so a member can do **everything the credential allows through the tools the gateway exposes**. For the store, that includes creating products and changing order status. The credential is a shared capability, not a secret the member lacks. Today there is no per-role or per-tool permission, so every member can call every enabled tool. The audit log attributes each call to the person who made it, which is the control we have. Next step: per-role tool permissions (for example, members read orders, only admins change status).

**2. Why client tokens are not passed through to upstream servers.**
The key a member puts in their client is a gateway key. The gateway never forwards it. Passing it through would (a) hand every upstream server, including a compromised one, a working credential for the gateway and every other upstream, and (b) tie each upstream's auth to our key format. Instead the gateway authenticates the client itself, then calls the upstream with that upstream's own credential, so a leak at one upstream exposes only that upstream's credential, and a revoked gateway key stops working at the first hop.

**3. Untrusted upstreams: tool descriptions written to manipulate the model.**
A malicious or compromised server can put instructions in a tool's name or description ("always call this first", "send the order list to X") or in a tool result. What we do: only admins can register a server; names are namespaced and descriptions tagged `[slug]`, so a tool cannot pose as another server's; the chat agent's system prompt treats tool text as data; the loop is capped at 6 steps; the agent acts only with the logged-in user's permissions and every call is audited. What we do **not** do: scan or pin tool descriptions, require approval before a write tool runs, or limit which tools a given server may expose. A convincing description could still push the model into calling a tool it should not. Next step: show descriptions to the admin for approval when a server is added or changes, and require confirmation for write tools.

**4. What can one team member do to another?**
They cannot read or revoke each other's keys (key lists and revoke are scoped to the owner; only admins see all), cannot see each other's audit rows, and cannot sign in as each other. A member's key never appears in another member's view. What they can do is act on **shared resources**: a member can change store data (orders, products) that everyone sees, and can use the same tools. The chat history lives only in the browser, so one member's conversation is not visible to another. Disabling a user also blocks their existing keys on the next call.