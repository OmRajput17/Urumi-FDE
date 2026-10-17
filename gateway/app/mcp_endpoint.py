"""The gateway as an MCP server (Streamable HTTP) for external clients.

Auth: the client sends its personal API key as a Bearer token. We hash it, look it up, and
remember who it is for the duration of this one request in a context variable, so the tool
handlers know which user to audit. The key itself is never forwarded to any upstream.
"""
from contextvars import ContextVar

import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.responses import JSONResponse

from . import core

CURRENT_USER: ContextVar[dict] = ContextVar("current_user")

server = Server("team-mcp-gateway")


@server.list_tools()
async def _list_tools() -> list[types.Tool]:
    user = CURRENT_USER.get()
    return [
        types.Tool(name=t["name"], description=t["description"], inputSchema=t["inputSchema"])
        for t in core.list_tools_for(user)
    ]


# validate_input=False: the upstream server validates arguments against its own schema.
@server.call_tool(validate_input=False)
async def _call_tool(name: str, arguments: dict | None):
    user = CURRENT_USER.get()
    try:
        result = await core.call_tool(user, name, arguments)
    except core.GatewayError as exc:
        raise ValueError(str(exc)) from None  # becomes an isError result with this message
    if result.isError:
        text = next((c.text for c in result.content if getattr(c, "text", None)), "tool reported an error")
        raise ValueError(text)
    return result.content


# stateless=True: no session lives in this pod's memory, so any replica can serve any request.
manager = StreamableHTTPSessionManager(app=server, stateless=True, json_response=True)


class McpAuthApp:
    """ASGI wrapper: authenticate the API key, then hand the request to the MCP session manager."""

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return
        headers = dict(scope["headers"])
        auth = headers.get(b"authorization", b"").decode()
        key = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        user = core.authenticate_api_key(key) if key else None
        if not user:
            response = JSONResponse(
                {"error": "Invalid or revoked API key"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return
        token = CURRENT_USER.set(user)
        try:
            await manager.handle_request(scope, receive, send)
        finally:
            CURRENT_USER.reset(token)


mcp_app = McpAuthApp()