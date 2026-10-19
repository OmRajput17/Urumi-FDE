"""Upstream #2: a small utility MCP server (time and arithmetic). No credentials needed.

Why it exists: "what orders came in today?" needs today's date, and the store's order tool
cannot know it. With this server the model first asks for the start of today, then passes
that to the store. That is one prompt using two different upstream servers.
"""
import ast
import datetime
import operator
import os
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import PlainTextResponse

PORT = int(os.environ.get("PORT", "8000"))
mcp = FastMCP("utils", host="0.0.0.0", port=PORT, stateless_http=True, json_response=True)


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(f"Unknown timezone '{name}'. Use names like 'UTC' or 'Asia/Kolkata'.") from None


@mcp.tool()
async def current_time(timezone: str = "UTC") -> str:
    """Current date and time in an IANA timezone (for example 'UTC' or 'Asia/Kolkata'), as ISO 8601."""
    return datetime.datetime.now(_zone(timezone)).isoformat(timespec="seconds")


@mcp.tool()
async def start_of_today(timezone: str = "UTC", days_ago: int = 0) -> str:
    """Midnight at the start of a day in an IANA timezone, as ISO 8601 without an offset
    (for example 2026-10-17T00:00:00). days_ago=0 is today, 1 is yesterday, and so on.
    Use it for created_after / created_before when asking the store for orders.
    The store keeps its clock in UTC, so pass 'UTC' for store queries."""
    if not 0 <= days_ago <= 3650:
        raise ValueError("days_ago must be between 0 and 3650.")
    now = datetime.datetime.now(_zone(timezone))
    day = now.replace(hour=0, minute=0, second=0, microsecond=0) - datetime.timedelta(days=days_ago)
    return day.strftime("%Y-%m-%dT%H:%M:%S")


_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}


def _eval(node):
    """Evaluate only numbers and arithmetic. Never calls eval(), so nothing else can run."""
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _eval(node.operand)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError("Exponent too large (limit 100).")
        return _OPS[type(node.op)](left, right)
    raise ValueError("Only numbers and + - * / // % ** ( ) are allowed.")


@mcp.tool()
async def calculate(expression: str) -> str:
    """Evaluate a basic arithmetic expression such as '(499 * 3) * 1.18'.
    Supports + - * / // % ** and parentheses."""
    if len(expression) > 200:
        raise ValueError("Expression too long (limit 200 characters).")
    try:
        result = _eval(ast.parse(expression.strip(), mode="eval"))
    except ZeroDivisionError:
        raise ValueError("Division by zero.") from None
    except SyntaxError:
        raise ValueError("Could not read that expression.") from None
    return str(result)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")