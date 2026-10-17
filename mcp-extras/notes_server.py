"""Upstream #3: a tiny notes MCP server that REQUIRES a bearer token.

Why it exists: it proves the gateway's credential handling. The admin registers this server
with the token once. Members use its tools through the gateway and never see the token.
Notes live in memory (one replica), which is fine for a demo.
"""
import datetime
import hmac
import os

import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import PlainTextResponse

TOKEN = os.environ["NOTES_TOKEN"]  # from a Kubernetes Secret
PORT = int(os.environ.get("PORT", "8000"))
MAX_NOTES = 500

mcp = FastMCP("notes", host="0.0.0.0", port=PORT, stateless_http=True, json_response=True)
_notes: list[dict] = []


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


@mcp.tool()
async def add_note(text: str) -> dict:
    """Save a short note and return it with its id."""
    text = text.strip()
    if not text:
        raise ValueError("Note text must not be empty.")
    if len(_notes) >= MAX_NOTES:
        raise ValueError(f"Note limit reached ({MAX_NOTES}).")
    note = {
        "id": len(_notes) + 1,
        "text": text[:1000],
        "created": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
    }
    _notes.append(note)
    return note


@mcp.tool()
async def list_notes() -> list[dict]:
    """List all saved notes, oldest first."""
    return _notes


inner = mcp.streamable_http_app()


async def app(scope, receive, send):
    """Require 'Authorization: Bearer <token>' on everything except the health probe."""
    if scope["type"] == "http" and scope["path"] != "/health":
        auth = dict(scope["headers"]).get(b"authorization", b"").decode()
        if not hmac.compare_digest(auth, f"Bearer {TOKEN}"):
            await send({"type": "http.response.start", "status": 401, "headers": [(b"content-type", b"text/plain")]})
            await send({"type": "http.response.body", "body": b"unauthorized"})
            return
    await inner(scope, receive, send)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")