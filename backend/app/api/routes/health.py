from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from starlette.concurrency import run_in_threadpool

from app.core.config import API_VERSION, Settings, get_app_settings
from app.db.session import database_is_reachable
from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service health check",
    responses={503: {"model": HealthResponse, "description": "Database unavailable"}},
)
async def health(
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> HealthResponse:
    """Reports API status and database connectivity. Returns 503 if the database is down."""
    database_ok = await run_in_threadpool(database_is_reachable, request.app.state.engine)
    if not database_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        status="ok" if database_ok else "degraded",
        service=settings.app_name,
        version=API_VERSION,
        environment=settings.app_env.value,
        database="ok" if database_ok else "unavailable",
    )
