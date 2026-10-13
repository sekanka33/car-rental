from fastapi import APIRouter

from app.api.deps import DbSession, OwnerUser
from app.core.errors import NotFoundError
from app.models import OwnerProfile
from app.schemas.auth import OwnerProfileResponse

router = APIRouter(prefix="/owners", tags=["owners"])


@router.get("/me/profile", response_model=OwnerProfileResponse)
def read_owner_profile(user: OwnerUser, session: DbSession) -> OwnerProfile:
    """Owner-only. Vehicle management endpoints are added in Stage 07."""
    profile = session.query(OwnerProfile).filter_by(user_id=user.id).one_or_none()
    if profile is None:
        raise NotFoundError("Owner profile not found.")
    return profile
