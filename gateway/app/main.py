import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import api, core, db
from .mcp_endpoint import manager, mcp_app


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    core.seed()
    refresher = asyncio.create_task(core.refresh_loop())
    try:
        async with manager.run():  # starts the MCP session manager's task group
            yield
    finally:
        refresher.cancel()


app = FastAPI(title="Team MCP Gateway", lifespan=lifespan)
app.include_router(api.router)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


# The single MCP endpoint. Registered as a raw ASGI app so "/mcp" never redirects to "/mcp/"
# (MCP clients do not follow redirects on POST).
app.add_route("/mcp", mcp_app)
app.add_route("/mcp/", mcp_app)