# WooCommerce MCP server

An MCP server (Streamable HTTP, stateless) that exposes a WooCommerce store as tools. It is registered in the gateway as the first upstream server and is not reachable from outside the cluster (a NetworkPolicy admits only the gateway pod).

| Tool | What it does |
|---|---|
| `list_products(per_page, search)` | Products with id, name, price, status, stock |
| `create_product(name, regular_price)` | Creates and publishes a simple product |
| `list_orders(status, created_after, created_before, per_page)` | Orders, newest first, optionally limited to a UTC time range |
| `get_order(order_id)` | One order with customer and items |
| `update_order_status(order_id, status)` | Changes an order's status (validated against the allowed list) |

## Configuration (environment variables)

| Variable | Meaning |
|---|---|
| `WC_BASE_URL` | Store URL inside the cluster |
| `WC_KEY`, `WC_SECRET` | WooCommerce REST API credentials, injected from a Kubernetes Secret |

The store only accepts key/secret Basic auth over HTTPS. Inside the cluster the call is plain HTTP, so the server sends `X-Forwarded-Proto: https`, which the WordPress image honours.

## Run and check

```
uv sync
set WC_BASE_URL=http://localhost:8080 && set WC_KEY=... && set WC_SECRET=...
uv run python server.py        # serves http://localhost:8000/mcp, health at /health
```

Errors from the store come back as clear tool errors (`WooCommerce returned 401: ...`), not stack traces. Order times are UTC.