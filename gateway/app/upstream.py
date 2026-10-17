"""MCP client side: talk to one upstream server over Streamable HTTP.

Every operation opens its own short-lived session. Upstreams are stateless, so there is
no connection to keep alive, and a dead or slow upstream can only ever hurt the one call
that is talking to it.
"""
import asyncio
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


class UpstreamError(Exception):
    """A failure with a message that is safe and useful to show to a user."""


def _headers(server: dict) -> dict[str, str]:
    cred = server.get("credential")
    if not cred or server["auth_type"] == "none":
        return {}
    if server["auth_type"] == "bearer":
        return {"Authorization": f"Bearer {cred}"}
    return {server.get("auth_header_name") or "X-API-Key": cred}


def _explain(exc: BaseException) -> str:
    """Turn nested task-group errors into one short readable line."""
    if isinstance(exc, BaseExceptionGroup):
        return _explain(exc.exceptions[0])
    name = type(exc).__name__
    text = str(exc).strip()
    return f"{name}: {text}" if text else name


async def _run(server: dict, timeout: float, fn):
    try:
        async with asyncio.timeout(timeout):
            async with streamablehttp_client(server["url"], headers=_headers(server)) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await fn(session)
    except TimeoutError:
        raise UpstreamError(f"timed out after {timeout:g}s") from None
    except UpstreamError:
        raise
    except Exception as exc:  # connection refused, DNS failure, HTTP 4xx/5xx, protocol errors
        raise UpstreamError(_explain(exc)) from None


async def list_tools(server: dict, timeout: float) -> list[dict[str, Any]]:
    async def fn(session: ClientSession):
        result = await session.list_tools()
        return [
            {
                "name": t.name,
                "description": t.description or "",
                "inputSchema": t.inputSchema,
            }
            for t in result.tools
        ]

    return await _run(server, timeout, fn)


async def call_tool(server: dict, tool: str, arguments: dict | None, timeout: float):
    async def fn(session: ClientSession):
        return await session.call_tool(tool, arguments or {})

    return await _run(server, timeout, fn)