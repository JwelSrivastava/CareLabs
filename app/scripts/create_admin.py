"""Create or promote an admin account from environment variables."""

import os
import sys
from collections.abc import Mapping

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.user import User, UserRole
from app.repositories.user_repository import get_user_by_email
from app.schemas.auth import SignupRequest

PLACEHOLDER_PASSWORDS = {"change-me", "change-me-admin-password"}


class AdminConfigError(Exception):
    """Raised when the admin environment variables are missing or unsafe."""


def load_admin_config(env: Mapping[str, str]) -> tuple[str, str, str]:
    password = env.get("ADMIN_PASSWORD", "")
    if password in PLACEHOLDER_PASSWORDS:
        raise AdminConfigError("Set ADMIN_PASSWORD to a value other than the example placeholder.")
    try:
        data = SignupRequest(
            name=env.get("ADMIN_NAME", ""),
            email=env.get("ADMIN_EMAIL", ""),
            password=password,
        )
    except ValidationError as exc:
        raise AdminConfigError("ADMIN_NAME, ADMIN_EMAIL, and ADMIN_PASSWORD must be valid.") from exc
    return data.name, data.email, data.password


def create_admin(name: str, email: str, password: str) -> str:
    db = SessionLocal()
    try:
        user = get_user_by_email(db, email)
        if user is None:
            db.add(
                User(
                    name=name,
                    email=email,
                    password_hash=hash_password(password),
                    role=UserRole.ADMIN,
                )
            )
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                user = get_user_by_email(db, email)
                if user is None:
                    raise
            else:
                return "created"
        if user.role == UserRole.ADMIN:
            return "exists"
        user.role = UserRole.ADMIN
        db.commit()
        return "promoted"
    finally:
        db.close()


def main() -> None:
    try:
        name, email, password = load_admin_config(os.environ)
    except AdminConfigError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from None
    result = create_admin(name, email, password)
    print(f"{result}: {email}")


if __name__ == "__main__":
    main()
