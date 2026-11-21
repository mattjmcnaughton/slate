"""Health check endpoints (unauthenticated)."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from slate.deps import ContainerDep

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict:
    """Liveness probe."""
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(container: ContainerDep):  # noqa: ANN201
    """Readiness probe: the storage answers a query."""
    try:
        async with container.uow_factory() as uow:
            await uow.settings.get()
    except Exception:
        return JSONResponse({"status": "not ready", "database": "unreachable"}, status_code=503)
    return {"status": "ready"}
