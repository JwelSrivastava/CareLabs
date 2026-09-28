import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import verify_password
from app.main import app
from app.models.user import User

client = TestClient(app)


def _email() -> str:
    return f"{uuid.uuid4()}@example.com"


def _delete_user(email: str) -> None:
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email == email))
        if user is not None:
            db.delete(user)
            db.commit()
    finally:
        db.close()


def test_signup_creates_a_user_without_storing_plaintext() -> None:
    email = _email()
    try:
        response = client.post(
            "/api/v1/auth/signup",
            json={"name": "John Doe", "email": email, "password": "StrongPassword123"},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["email"] == email
        assert body["name"] == "John Doe"
        assert body["role"] == "USER"
        assert "password" not in body
        assert "password_hash" not in body

        db = SessionLocal()
        try:
            user = db.scalar(select(User).where(User.email == email))
            assert user is not None
            assert user.password_hash != "StrongPassword123"
            assert verify_password("StrongPassword123", user.password_hash) is True
        finally:
            db.close()
    finally:
        _delete_user(email)


def test_signup_rejects_a_duplicate_email() -> None:
    email = _email()
    payload = {"name": "John Doe", "email": email, "password": "StrongPassword123"}
    try:
        first = client.post("/api/v1/auth/signup", json=payload)
        assert first.status_code == 201
        second = client.post(
            "/api/v1/auth/signup",
            json={"name": "Jane Doe", "email": email.upper(), "password": "StrongPassword123"},
        )
        assert second.status_code == 409
        assert second.json()["detail"] == "Email is already registered"
    finally:
        _delete_user(email)


def test_signup_rejects_invalid_input() -> None:
    response = client.post(
        "/api/v1/auth/signup",
        json={"name": " ", "email": "not-an-email", "password": "short", "role": "ADMIN"},
    )
    assert response.status_code == 422
