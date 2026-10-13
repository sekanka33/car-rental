"""Operator command line. Administrator accounts can only be created here, never via the API.

    python -m app.cli create-admin --email ceo@example.co.za --full-name "Jane Doe"

The password is read interactively (not echoed, never a command-line argument, so it
does not end up in shell history or process lists). Use --password-stdin for automation.
"""

import argparse
import getpass
import sys
from collections.abc import Callable

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.schemas.auth import FullName, Password
from app.services.accounts import create_admin

PasswordReader = Callable[[str], str]


def create_admin_command(
    session: Session,
    *,
    email: str,
    full_name: str,
    read_password: PasswordReader,
    password_from_stdin: bool = False,
) -> int:
    try:
        email = str(TypeAdapter(EmailStr).validate_python(email))
    except ValidationError:
        print("Error: invalid email address.", file=sys.stderr)
        return 2
    try:
        TypeAdapter(FullName).validate_python(full_name)
    except ValidationError:
        print("Error: full name must be 2-200 characters.", file=sys.stderr)
        return 2

    if password_from_stdin:
        password = sys.stdin.readline().rstrip("\n")
    else:
        password = read_password("Password: ")
        if read_password("Confirm password: ") != password:
            print("Error: passwords do not match.", file=sys.stderr)
            return 2
    try:
        TypeAdapter(Password).validate_python(password)
    except ValidationError:
        print("Error: password must be 8-128 characters.", file=sys.stderr)
        return 2

    try:
        user = create_admin(session, email=email, full_name=full_name, password=password)
    except AppError as exc:
        print(f"Error: {exc.message}", file=sys.stderr)
        return 1
    print(f"Administrator created: {user.email} (id {user.id})")
    return 0


def seed_demo_command(session: Session, settings) -> int:
    from app.demo_data import DemoDataRefusedError, seed_demo_data
    from app.integrations.storage import LocalDocumentStorage

    try:
        created = seed_demo_data(
            session, settings, LocalDocumentStorage(settings.document_storage_dir)
        )
    except DemoDataRefusedError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Demo data: {created} vehicles created." if created else "Demo data already present.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    admin = commands.add_parser("create-admin", help="Create an administrator account")
    admin.add_argument("--email", required=True)
    admin.add_argument("--full-name", required=True)
    admin.add_argument(
        "--password-stdin", action="store_true", help="Read the password from standard input"
    )
    commands.add_parser(
        "seed-demo-data",
        help="DEVELOPMENT ONLY: create demo owners, approved vehicles, photos and prices",
    )
    args = parser.parse_args(argv)

    from app.core.config import get_settings
    from app.db.session import build_engine, build_session_factory

    settings = get_settings()
    engine = build_engine(settings.database_url.get_secret_value())
    try:
        with build_session_factory(engine)() as session:
            if args.command == "seed-demo-data":
                return seed_demo_command(session, settings)
            return create_admin_command(
                session,
                email=args.email,
                full_name=args.full_name,
                read_password=getpass.getpass,
                password_from_stdin=args.password_stdin,
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
