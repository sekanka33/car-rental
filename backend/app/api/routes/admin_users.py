import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import AdminUser, DbSession
from app.repositories import users as repo
from app.schemas.auth import AdminUserResponse, SuspendUserRequest, UserListResponse
from app.services import accounts

router = APIRouter(prefix="/admin/users", tags=["admin: users"])


@router.get("", response_model=UserListResponse)
def list_users(
    _: AdminUser,
    session: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> UserListResponse:
    users, total = repo.list_users(session, limit=limit, offset=offset)
    return UserListResponse(
        items=[AdminUserResponse.from_user(u) for u in users],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/{user_id}/suspend", response_model=AdminUserResponse)
def suspend_user(
    user_id: uuid.UUID, body: SuspendUserRequest, admin: AdminUser, session: DbSession
) -> AdminUserResponse:
    """Suspend an account: signs the user out everywhere and blocks further access."""
    user = accounts.suspend_user(session, actor=admin, user_id=user_id, reason=body.reason)
    return AdminUserResponse.from_user(user)


@router.post("/{user_id}/reactivate", response_model=AdminUserResponse)
def reactivate_user(user_id: uuid.UUID, admin: AdminUser, session: DbSession) -> AdminUserResponse:
    user = accounts.reactivate_user(session, actor=admin, user_id=user_id)
    return AdminUserResponse.from_user(user)
