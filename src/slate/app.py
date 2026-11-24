"""FastAPI application factory.

``create_app(container)`` takes a fully built container, so tests inject fakes.
The module-level ``app`` (for uvicorn) builds one from environment settings.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from slate.config import Settings
from slate.container import Container, build_container
from slate.logging import configure_logging
from slate.mcp_server import MountMCP, create_mcp_app
from slate.routers import agent, api, auth, health
from slate.services.agent import AgentTurns
from slate.web.serve import mount_frontend

DESCRIPTION = """\
Slate's JSON API. Every record belongs to your workspace; ids are UUIDs, and task
routes also accept keys such as `SLT-12`. Another workspace's id answers 404.

**Authentication.** Browsers use the session cookie set at sign-in. Scripts send
`Authorization: Bearer <key>` with a **REST** key from Settings → API keys (use
*Authorize* above). Keys act as you, in your workspace, and revoking one takes
effect on the next request. Keys cannot manage keys, change settings, change the
assistant, or apply Pending changes: those need a browser session.

**MCP.** AI clients (Claude Code, Codex, Amp) connect to `/mcp` (Streamable HTTP)
with an **MCP** key. MCP keys work only there, and REST keys are refused there.
The MCP tools are the same 13 the sidebar assistant uses.

**Agent mode.** Writes from the assistant and MCP clients follow your workspace's
Agent mode: `suggest` stores them as Pending changes for you to apply, `apply`
runs them at once. Deletes always wait for you.
"""


def create_app(container: Container, *, serve_frontend: bool = True) -> FastAPI:
    mcp = create_mcp_app(container)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        for step in container.startup:
            await step(container)
        async with mcp.router.lifespan_context(mcp):
            yield
        for step in container.shutdown:
            await step()

    app = FastAPI(
        title="Slate",
        description=DESCRIPTION,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.container = container
    app.state.agent_turns = AgentTurns(container)

    @app.middleware("http")
    async def same_origin_writes(request: Request, call_next):  # noqa: ANN001, ANN202
        # Cookie-authenticated writes must come from our own pages (CSRF). Bearer
        # requests carry no ambient credentials, so they are exempt.
        if request.method not in ("GET", "HEAD", "OPTIONS") and not request.headers.get(
            "authorization"
        ):
            origin = request.headers.get("origin")
            if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
                host = request.headers.get("host", "")
                if origin.split("://", 1)[-1] != host:
                    return JSONResponse({"detail": "Cross-origin request refused"}, 403)
        return await call_next(request)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(api.router)
    app.include_router(agent.router)
    app.add_middleware(MountMCP, mcp=mcp)
    if serve_frontend:
        mount_frontend(app)
    return app


def _from_env() -> FastAPI:
    settings = Settings()
    configure_logging(settings)
    return create_app(build_container(settings))


app = _from_env()
