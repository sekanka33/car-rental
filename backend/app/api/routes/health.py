from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.config import API_VERSION, Settings, get_app_settings
from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Service health check")
def health(settings: Annotated[Settings, Depends(get_app_settings)]) -> HealthResponse:
    """Liveness check. Database connectivity is added to this check in Stage 04."""
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=API_VERSION,
        environment=settings.app_env.value,
    )
