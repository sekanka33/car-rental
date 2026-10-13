import subprocess
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cli import create_admin_command
from app.models import AuditLog, User
from app.models.enums import RoleName
from tests.conftest import BACKEND_DIR, requires_db

pytestmark = requires_db
PASSWORD = "operator-chosen-passphrase"


def reader(*answers: str):
    replies = iter(answers)
    return lambda prompt: next(replies)


def test_create_admin(db_session: Session, capsys) -> None:
    code = create_admin_command(
        db_session,
        email="CEO@Example.co.za",
        full_name="Platform Owner",
        read_password=reader(PASSWORD, PASSWORD),
    )

    assert code == 0
    assert "Administrator created: ceo@example.co.za" in capsys.readouterr().out
    user = db_session.scalar(select(User).where(User.email == "ceo@example.co.za"))
    assert [role.name for role in user.roles] == [RoleName.ADMIN]
    assert user.email_verified_at is not None
    assert user.password_hash.startswith("$argon2id$")
    audit = db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(user.id)))
    assert audit.action == "admin.created" and audit.actor_user_id is None
    assert PASSWORD not in str(audit.changes)


def test_create_admin_rejects_bad_input(db_session: Session) -> None:
    def run(email="a@example.com", name="Admin Person", answers=(PASSWORD, PASSWORD)) -> int:
        return create_admin_command(
            db_session, email=email, full_name=name, read_password=reader(*answers)
        )

    assert run(answers=(PASSWORD, "different")) == 2
    assert run(answers=("short", "short")) == 2
    assert run(email="not-an-email") == 2
    assert run(name="A") == 2
    assert db_session.scalar(select(User).where(User.email == "a@example.com")) is None

    assert run() == 0
    assert run() == 1  # already exists


def test_cli_entry_point_help() -> None:
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "app.cli", "create-admin", "--help"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--email" in result.stdout and "--password" not in result.stdout.replace(
        "--password-stdin", ""
    )
