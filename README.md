# Team MCP Gateway on Kubernetes (WooCommerce first)

A WooCommerce store, an MCP server for it, and a **team MCP gateway** with a dashboard and chat agent, all on Kubernetes. An admin registers MCP servers once. Every teammate then uses all of them through **one URL and one personal key**, from an MCP client or from the chat in the dashboard. Every tool call is audited.

* Design and tradeoffs: [docs/DESIGN.md](docs/DESIGN.md)
* Threat model: [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md)

## What is in the repo

| Folder | What it is |
|---|---|
| `store/` | Helm chart: WordPress + WooCommerce + MySQL, persistent volumes, Ingress |
| `mcp-woo/` | WooCommerce MCP server (Python, FastMCP) + its Helm chart |
| `mcp-extras/` | Two small extra MCP servers (`utils`: time and arithmetic, `notes`: in-memory notes) + chart |
| `gateway/` | Backend: MCP endpoint `/mcp`, admin API `/api`, auth, audit, chat agent (FastAPI + SQLite) + chart + tests |
| `dashboard/` | React dashboard (Vite), served by non-root nginx + chart |
| `kind-config.yaml`, `traefik-values.yaml` | Local cluster and ingress controller settings |

Every chart has `values.yaml` (defaults), `values-local.yaml` and `values-prod.yaml`. **Local and production use the same charts; only the values file changes.**

## URLs (local)

| What | URL |
|---|---|
| Storefront and WordPress admin | http://store.localhost/ and http://store.localhost/wp-admin |
| Dashboard | http://dashboard.localhost/ |
| MCP endpoint (for clients) | http://dashboard.localhost/mcp |

`*.localhost` names resolve to 127.0.0.1 in browsers and curl, so no DNS setup is needed. kind publishes the cluster's ports 80/443 on your machine (`extraPortMappings` in `kind-config.yaml`) and Traefik routes by hostname. Node.js tools (MCP Inspector) do not resolve `*.localhost`; add `127.0.0.1 dashboard.localhost` and `127.0.0.1 store.localhost` to your hosts file for them.

## Local setup

Needs: Docker, kind, kubectl, Helm, and (for development) uv and Node 22.

```bash
# 1. Cluster and ingress controller
kind create cluster --name urumi --config kind-config.yaml
helm repo add traefik https://traefik.github.io/charts
helm install traefik traefik/traefik -n traefik --create-namespace -f traefik-values.yaml

# 2. Store (choose your own passwords)
helm install store ./store -n store --create-namespace \
  --set mysql.rootPassword=CHANGE_ME --set mysql.password=CHANGE_ME_TOO
```

Open http://store.localhost/ and finish the WordPress installer. Then:

1. Install and activate the **WooCommerce** plugin and complete its basic setup.
2. **Settings → Permalinks → Post name** (the REST API needs pretty permalinks).
3. **WooCommerce → Settings → Payments → Cash on delivery: enable** (the test-friendly checkout).
4. **WooCommerce → Settings → Advanced → REST API → Add key**, permission *Read/Write*. Copy the key and secret (shown once).

```bash
# 3. Build and load the images
docker build -t mcp-woo:0.1.1    ./mcp-woo
docker build -t mcp-extras:0.1.1 ./mcp-extras
docker build -t gateway:0.1.0    ./gateway
docker build -t dashboard:0.1.0  ./dashboard
kind load docker-image mcp-woo:0.1.1 mcp-extras:0.1.1 gateway:0.1.0 dashboard:0.1.0 --name urumi

# 4. Install the rest. Gateway namespace first, so the NetworkPolicies have a target.
kubectl create namespace gateway
helm install mcp-woo ./mcp-woo/chart -n store --set image.tag=0.1.1 \
  --set wc.key=ck_XXX --set wc.secret=cs_XXX
helm install mcp-extras ./mcp-extras/chart -n extras --create-namespace --set image.tag=0.1.1 \
  --set notesToken=CHANGE_ME
helm install gateway ./gateway/chart -n gateway -f gateway/chart/values-local.yaml \
  --set admin.password=CHANGE_ME --set sessionSecret=CHANGE_ME_LONG_RANDOM \
  --set llm.apiKey=YOUR_GROQ_KEY
helm install dashboard ./dashboard/chart -n gateway -f dashboard/chart/values-local.yaml

kubectl get pods -A     # everything should become Running
```

Secrets are passed with `--set` and live in Kubernetes Secrets. Nothing secret is in the repo.

Sign in at http://dashboard.localhost/ as `admin@example.com` with the admin password you chose. The WooCommerce server is already registered. Add the others under **Servers → Add server**:

| Slug | URL | Credential |
|---|---|---|
| `utils` | `http://utils.extras.svc.cluster.local:8000/mcp` | none |
| `notes` | `http://notes.extras.svc.cluster.local:8000/mcp` | Bearer token = your `notesToken` |

## Use it

**Place an order.** Open http://store.localhost/, add a product to the cart, check out with *Cash on delivery*. The order appears in **wp-admin → WooCommerce → Orders**.

**Chat agent.** Dashboard → **Chat**. Try: "Create a product called Test Mug at 12.99", then "What orders came in today?" The reply lists the tools it called (click *Show tool details* for arguments and results). The agent calls tools **as the signed-in user**, through the same code path and audit log as an external client.

**Connect an MCP client (any teammate).**

1. Sign in, open **Team & keys**, name a key, click **Generate key**, copy it (shown once).
2. Claude Code:
   ```bash
   claude mcp add --transport http gateway http://dashboard.localhost/mcp \
     --header "Authorization: Bearer YOUR_KEY"
   ```
   Cursor or any client with HTTP MCP support: URL `http://dashboard.localhost/mcp`, header `Authorization: Bearer YOUR_KEY`.
3. You see every enabled server's tools, named `server__tool` (for example `woocommerce__list_orders`). You never see the upstream credentials.

**Admin tasks.** Servers: add, edit, disable, remove, check now. Team & keys: invite members, disable them, revoke any key. Audit log: who called which tool, when, how long, and the result.

## Tests

```bash
cd gateway
uv sync
uv run python tests/smoke.py        # gateway against two fake upstreams (auth, routing, failure, revoke, audit)
uv run python tests/agent_test.py   # chat agent against a fake LLM
```

Dashboard development: `cd dashboard && npm install && npm run dev` (proxies `/api` to `GATEWAY_URL`, default http://localhost:9000).

## Production-like VPS (k3s)

The same charts, with `values-prod.yaml`.

1. **Server.** A Linux VPS with ports 80 and 443 open. Install k3s: `curl -sfL https://get.k3s.io | sh -`. k3s already ships **Traefik** and the **local-path** StorageClass, so skip the Traefik install.
2. **DNS.** Point two A records at the VPS: the store (for example `store.example.com`) and the gateway/dashboard (for example `gateway.example.com`).
3. **TLS (optional but recommended).** Install cert-manager and create a `ClusterIssuer` named `letsencrypt-prod`. The prod values use it.
4. **Images.** Push the four images to a registry (for example `ghcr.io/YOUR_USER/...`) and set `image.repository` in each `values-prod.yaml`, or import them on the node: `docker save gateway:0.1.0 | sudo k3s ctr images import -`.
5. **Install** exactly as in the local steps, but use `-f <chart>/values-prod.yaml` and your real secrets. Install the **store first and fresh**, because WordPress stores its address in the database at setup, so it must be installed under the real domain.

### What changes between local and VPS (all in values)

| Setting | Local (`values-local.yaml`) | VPS (`values-prod.yaml`) |
|---|---|---|
| Domains | `store.localhost`, `dashboard.localhost` | your domains |
| Ingress class | `traefik` (installed by us) | `traefik` (built into k3s) |
| TLS | off | on, via cert-manager annotation + `tls.secretName` |
| StorageClass | cluster default (`standard` in kind) | `local-path`, larger volumes |
| Images | built and `kind load`ed | pulled from a registry or imported |
| Secrets | `--set` on the command line | the same, from your secret manager or shell |

Gateway and dashboard share one host: the gateway's Ingress claims `/api` and `/mcp`, the dashboard's claims `/`, and the longer paths win. Only the dashboard Ingress requests the certificate; the gateway reuses the same TLS Secret.

## Upgrade and roll back

```bash
helm upgrade gateway ./gateway/chart -n gateway --reuse-values -f gateway/chart/values-local.yaml
helm history gateway -n gateway          # list revisions
helm rollback gateway 3 -n gateway       # go back to revision 3
```

`--reuse-values` keeps the secrets you set at install time. To ship a new image, build it with a new tag, load or push it, then `helm upgrade ... --set image.tag=NEW`. A rollback restores the previous chart and image. **Data is not rolled back**: the store database, WordPress files and the gateway's SQLite file stay as they are, so back them up before an upgrade that changes data.

## Known limits

See the tables in [docs/DESIGN.md](docs/DESIGN.md) and [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md). In short: single gateway replica (SQLite), upstream credentials are not encrypted at rest, no login rate limiting, an admin can register any URL, and the chat agent has no approval step before write tools.