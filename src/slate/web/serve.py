"""Serve the built frontend in production, with SPA fallback to index.html."""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

FRONTEND_DIST = Path(__file__).parent / "frontend" / "dist"

# Paths owned by the backend; everything else is a client-side route.
BACKEND_PREFIXES = ("api/", "auth/", "docs", "openapi.json", "healthz", "readyz")


def mount_frontend(app: FastAPI, dist: Path = FRONTEND_DIST) -> None:
    if not dist.is_dir():
        return
    root = dist.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        if path.startswith(BACKEND_PREFIXES):
            raise HTTPException(404)
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            cache = "public, max-age=31536000, immutable" if path.startswith("assets/") else None
            return FileResponse(candidate, headers={"Cache-Control": cache} if cache else None)
        return FileResponse(root / "index.html", headers={"Cache-Control": "no-cache"})
