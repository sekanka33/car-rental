import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog


def record_audit(
    session: Session,
    *,
    actor_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | str,
    changes: dict[str, Any] | None = None,
) -> None:
    """Add an audit entry to the current transaction (committed with the change itself).

    Never put passwords, tokens or full ID/licence numbers in `changes`.
    """
    session.add(
        AuditLog(
            actor_user_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            changes=changes,
        )
    )
