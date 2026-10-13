from fastapi import APIRouter

from app.api.deps import DbSession, OwnerUser
from app.models import OwnerProfile
from app.schemas.auth import OwnerProfileResponse
from app.schemas.vehicles import OwnerProfileUpdate
from app.services import vehicles

router = APIRouter(prefix="/owners", tags=["owners"])


@router.get("/me/profile", response_model=OwnerProfileResponse)
def read_owner_profile(user: OwnerUser, session: DbSession) -> OwnerProfile:
    return vehicles.get_owner_profile(session, user)


@router.patch("/me/profile", response_model=OwnerProfileResponse)
def update_owner_profile(
    body: OwnerProfileUpdate, user: OwnerUser, session: DbSession
) -> OwnerProfile:
    return vehicles.update_owner_profile(session, user, **body.model_dump(exclude_unset=True))
