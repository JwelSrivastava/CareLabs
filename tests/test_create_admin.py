import uuid

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.user import User, UserRole
from app.scripts.create_admin import AdminConfigError, create_admin, load_admin_config


def test_load_admin_config_rejects_missing_and_placeholder_values() -> None:
    try:
        load_admin_config({})
    except AdminConfigError:
        pass
    else:
        raise AssertionError("missing admin settings should be rejected")

    try:
        load_admin_config(
            {
                "ADMIN_NAME": "Ada Admin",
                "ADMIN_EMAIL": "ada@example.com",
                "ADMIN_PASSWORD": "change-me-admin-password",
            }
        )
    except AdminConfigError:
        pass
    else:
        raise AssertionError("placeholder admin password should be rejected")


def test_create_admin_is_idempotent_and_can_promote() -> None:
    email = f"{uuid.uuid4()}@example.com"
    db = SessionLocal()
    try:
        db.add(
            User(
                name="Existing User",
                email=email,
                password_hash="not-used",
                role=UserRole.USER,
            )
        )
        db.commit()
    finally:
        db.close()

    try:
        assert create_admin("Ada Admin", email, "StrongPassword123") == "promoted"
        assert create_admin("Ada Admin", email, "StrongPassword123") == "exists"

        created_email = f"{uuid.uuid4()}@example.com"
        assert create_admin("New Admin", created_email, "StrongPassword123") == "created"
        db = SessionLocal()
        try:
            created = db.scalar(select(User).where(User.email == created_email))
            promoted = db.scalar(select(User).where(User.email == email))
            assert created is not None
            assert created.role == UserRole.ADMIN
            assert created.password_hash != "StrongPassword123"
            assert promoted is not None
            assert promoted.role == UserRole.ADMIN
        finally:
            db.close()
    finally:
        db = SessionLocal()
        try:
            for address in (email, created_email if "created_email" in locals() else None):
                if address is None:
                    continue
                user = db.scalar(select(User).where(User.email == address))
                if user is not None:
                    db.delete(user)
            db.commit()
        finally:
            db.close()
