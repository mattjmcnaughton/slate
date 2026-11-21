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
from slate.routers import api, auth, health
from slate.web.serve import mount_frontend


def create_app(container: Container, *, serve_frontend: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        for step in container.startup:
            await step(container)
        yield
        for step in container.shutdown:
            await step()

    app = FastAPI(
        title="Slate",
        description="Personal task manager. Authenticate with `Authorization: Bearer <token>`.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.container = container

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
    if serve_frontend:
        mount_frontend(app)
    return app


def _from_env() -> FastAPI:
    settings = Settings()
    configure_logging(settings)
    return create_app(build_container(settings))


app = _from_env()
