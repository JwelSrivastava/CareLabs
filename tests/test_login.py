import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import decode_access_token
from app.main import app
from app.models.user import User

client = TestClient(app)


def _email() -> str:
    return f"{uuid.uuid4()}@example.com"


def _delete_user(email: str) -> None:
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email == email.lower()))
        if user is not None:
            db.delete(user)
            db.commit()
    finally:
        db.close()


def _signup(email: str) -> None:
    response = client.post(
        "/api/v1/auth/signup",
        json={"name": "John Doe", "email": email, "password": "StrongPassword123"},
    )
    assert response.status_code == 201


def test_login_returns_a_bearer_token() -> None:
    email = _email()
    try:
        _signup(email)
        response = client.post(
            "/api/v1/auth/login",
            json={"email": email.upper(), "password": "StrongPassword123"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["token_type"] == "bearer"
        user_id = decode_access_token(body["access_token"])

        me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
        assert me.status_code == 200
        assert me.json()["email"] == email
        assert me.json()["id"] == user_id
        assert "password_hash" not in me.json()
    finally:
        _delete_user(email)


def test_login_rejects_an_invalid_password() -> None:
    email = _email()
    try:
        _signup(email)
        response = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "WrongPassword123"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid email or password"
    finally:
        _delete_user(email)


def test_login_rejects_an_unknown_email() -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": _email(), "password": "StrongPassword123"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_health_is_public() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_me_requires_a_token() -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
