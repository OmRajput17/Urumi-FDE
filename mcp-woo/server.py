import os
import httpx
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import PlainTextResponse

BASE_URL = os.environ["WC_BASE_URL"].rstrip("/")
KEY = os.environ["WC_KEY"]
SECRET = os.environ["WC_SECRET"]

VALID_STATUSES = {
    "pending", "processing", "on-hold", "completed", "cancelled", "refunded", "failed",
}

mcp = FastMCP(
    "woocommerce",
    host="0.0.0.0",
    port=8000,
    stateless_http=True,
    json_response=True,
)


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


async def wc(method: str, path: str, **kwargs):
    """Call the WooCommerce REST API and turn failures into clear errors."""
    async with httpx.AsyncClient(
        base_url=f"{BASE_URL}/wp-json/wc/v3",
        auth=(KEY, SECRET),
        headers={"X-Forwarded-Proto": "https"},
        timeout=10.0,
    ) as c:
        try:
            r = await c.request(method, path, **kwargs)
        except httpx.RequestError as e:
            raise ValueError(f"Could not reach the store: {type(e).__name__}") from e
    if r.status_code >= 400:
        msg = r.json().get("message", r.text) if r.content else r.reason_phrase
        raise ValueError(f"WooCommerce returned {r.status_code}: {msg}")
    return r.json()


def trim_order(o: dict) -> dict:
    b = o.get("billing", {})
    return {
        "id": o["id"],
        "status": o["status"],
        "total": o["total"],
        "currency": o["currency"],
        "created": o["date_created"],
        "customer": f"{b.get('first_name', '')} {b.get('last_name', '')}".strip(),
        "items": [
            {"name": i["name"], "quantity": i["quantity"]} for i in o.get("line_items", [])
        ],
    }


@mcp.tool()
async def list_products(per_page: int = 10, search: str = "") -> list[dict]:
    """List products in the store. Optionally filter by a search term."""
    params = {"per_page": per_page}
    if search:
        params["search"] = search
    data = await wc("GET", "/products", params=params)
    return [
        {
            "id": p["id"],
            "name": p["name"],
            "price": p["price"],
            "status": p["status"],
            "stock_status": p["stock_status"],
        }
        for p in data
    ]


@mcp.tool()
async def create_product(name: str, regular_price: str) -> dict:
    """Create and publish a simple product. regular_price is a string like '499'."""
    if not name.strip():
        raise ValueError("name must not be empty")
    float(regular_price)  # fails fast on a non-numeric price
    p = await wc(
        "POST",
        "/products",
        json={"name": name, "type": "simple", "regular_price": regular_price, "status": "publish"},
    )
    return {"id": p["id"], "name": p["name"], "price": p["price"], "link": p["permalink"]}


@mcp.tool()
async def list_orders(
    status: str = "any",
    created_after: str = "",
    created_before: str = "",
    per_page: int = 20,
) -> list[dict]:
    """List orders, newest first. status can be 'any' or an order status like 'processing'.
    created_after and created_before are ISO 8601 datetimes in UTC, e.g. 2026-10-17T00:00:00.
    For 'today' pass only created_after. For 'yesterday' pass both: created_after is the
    start of yesterday and created_before is the start of today."""
    params = {"status": status, "per_page": per_page, "orderby": "date", "order": "desc"}
    if created_after:
        params["after"] = created_after
    if created_before:
        params["before"] = created_before
    return [trim_order(o) for o in await wc("GET", "/orders", params=params)]


@mcp.tool()
async def get_order(order_id: int) -> dict:
    """Get one order by its ID, including customer and items."""
    return trim_order(await wc("GET", f"/orders/{order_id}"))


@mcp.tool()
async def update_order_status(order_id: int, status: str) -> dict:
    """Change an order's status. Allowed: pending, processing, on-hold,
    completed, cancelled, refunded, failed."""
    if status not in VALID_STATUSES:
        raise ValueError(f"status must be one of: {', '.join(sorted(VALID_STATUSES))}")
    return trim_order(await wc("PUT", f"/orders/{order_id}", json={"status": status}))


if __name__ == "__main__":
    mcp.run(transport="streamable-http")