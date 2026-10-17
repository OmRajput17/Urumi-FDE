"""A tiny fake upstream MCP server for testing the gateway.

Usage: python tests/fake_upstream.py <name> <port>
If REQUIRE_TOKEN is set, requests without 'Authorization: Bearer <token>' get HTTP 401.
Every fake server has a tool called "echo", so two of them collide on purpose.
"""
import asyncio
import os
import sys

import uvicorn
from mcp.server.fastmcp import FastMCP

name, port = sys.argv[1], int(sys.argv[2])
required = os.environ.get("REQUIRE_TOKEN")

mcp = FastMCP(name, host="127.0.0.1", port=port, stateless_http=True, json_response=True)


@mcp.tool()
async def echo(text: str) -> str:
    """Repeat the text back, prefixed with this server's name."""
    return f"{name}: {text}"


@mcp.tool()
async def slow(seconds: float) -> str:
    """Sleep for the given number of seconds, then answer."""
    await asyncio.sleep(seconds)
    return f"{name}: done after {seconds}s"


@mcp.tool()
async def explode() -> str:
    """Always fails, to test tool-level errors."""
    raise ValueError("boom from " + name)


inner = mcp.streamable_http_app()


async def app(scope, receive, send):
    if required and scope["type"] == "http":
        auth = dict(scope["headers"]).get(b"authorization", b"").decode()
        if auth != f"Bearer {required}":
            await send({"type": "http.response.start", "status": 401, "headers": [(b"content-type", b"text/plain")]})
            await send({"type": "http.response.body", "body": b"unauthorized"})
            return
    await inner(scope, receive, send)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")