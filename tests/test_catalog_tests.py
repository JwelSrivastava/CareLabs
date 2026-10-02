import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.main import app
from app.models.test import DiagnosticTest
from app.models.user import User, UserRole

client = TestClient(app)


def _create_account(role: UserRole) -> tuple[str, dict[str, str]]:
    email = f"{uuid.uuid4()}@example.com"
    db = SessionLocal()
    try:
        db.add(
            User(
                name="Test Admin" if role == UserRole.ADMIN else "Test User",
                email=email,
                password_hash=hash_password("StrongPassword123"),
                role=role,
            )
        )
        db.commit()
    finally:
        db.close()
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "StrongPassword123"},
    )
    assert response.status_code == 200
    return email, {"Authorization": f"Bearer {response.json()['access_token']}"}


def _delete_account(email: str) -> None:
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email == email))
        if user is not None:
            db.delete(user)
            db.commit()
    finally:
        db.close()


def _delete_test(test_id: str) -> None:
    db = SessionLocal()
    try:
        diagnostic_test = db.get(DiagnosticTest, uuid.UUID(test_id))
        if diagnostic_test is not None:
            db.delete(diagnostic_test)
            db.commit()
    finally:
        db.close()


def test_admin_creates_test_and_user_can_list_it() -> None:
    admin_email, admin_headers = _create_account(UserRole.ADMIN)
    user_email, user_headers = _create_account(UserRole.USER)
    test_id = None
    name = f"CBC {uuid.uuid4()}"
    try:
        created = client.post(
            "/api/v1/tests",
            json={"name": name, "description": "Measures blood cells"},
            headers=admin_headers,
        )
        assert created.status_code == 201
        body = created.json()
        test_id = body["id"]
        assert body["name"] == name
        assert body["description"] == "Measures blood cells"
        assert "price" not in body

        listing = client.get("/api/v1/tests?page=1&limit=100", headers=user_headers)
        assert listing.status_code == 200
        page = listing.json()
        assert page["page"] == 1
        assert page["limit"] == 100
        assert page["total"] >= 1
        assert any(item["id"] == test_id for item in page["items"])

        fetched = client.get(f"/api/v1/tests/{test_id}", headers=user_headers)
        assert fetched.status_code == 200
        assert fetched.json()["id"] == test_id
    finally:
        if test_id is not None:
            _delete_test(test_id)
        _delete_account(admin_email)
        _delete_account(user_email)


def test_normal_user_cannot_create_test() -> None:
    email, headers = _create_account(UserRole.USER)
    try:
        response = client.post(
            "/api/v1/tests",
            json={"name": "Blocked Test", "description": "Should not be created"},
            headers=headers,
        )
        assert response.status_code == 403
    finally:
        _delete_account(email)


def test_diagnostic_test_not_found() -> None:
    email, headers = _create_account(UserRole.USER)
    try:
        response = client.get(f"/api/v1/tests/{uuid.uuid4()}", headers=headers)
        assert response.status_code == 404
        assert response.json()["detail"] == "Test not found"
    finally:
        _delete_account(email)


def test_unauthenticated_test_list_is_rejected() -> None:
    response = client.get("/api/v1/tests")
    assert response.status_code == 401


def test_duplicate_test_name_conflicts() -> None:
    email, headers = _create_account(UserRole.ADMIN)
    name = f"Lipid Profile {uuid.uuid4()}"
    test_id = None
    try:
        first = client.post(
            "/api/v1/tests",
            json={"name": name, "description": "Cholesterol panel"},
            headers=headers,
        )
        assert first.status_code == 201
        test_id = first.json()["id"]
        second = client.post(
            "/api/v1/tests",
            json={"name": name, "description": "Another description"},
            headers=headers,
        )
        assert second.status_code == 409
    finally:
        if test_id is not None:
            _delete_test(test_id)
        _delete_account(email)


def test_admin_can_update_and_delete_test() -> None:
    email, headers = _create_account(UserRole.ADMIN)
    name = f"Thyroid {uuid.uuid4()}"
    test_id = None
    try:
        created = client.post(
            "/api/v1/tests",
            json={"name": name, "description": "Thyroid panel"},
            headers=headers,
        )
        assert created.status_code == 201
        test_id = created.json()["id"]
        updated = client.put(
            f"/api/v1/tests/{test_id}",
            json={"name": name, "description": "Updated thyroid panel"},
            headers=headers,
        )
        assert updated.status_code == 200
        assert updated.json()["description"] == "Updated thyroid panel"
        deleted = client.delete(f"/api/v1/tests/{test_id}", headers=headers)
        assert deleted.status_code == 204
        missing = client.get(f"/api/v1/tests/{test_id}", headers=headers)
        assert missing.status_code == 404
        test_id = None
    finally:
        if test_id is not None:
            _delete_test(test_id)
        _delete_account(email)


def test_normal_user_cannot_change_a_test() -> None:
    admin_email, admin_headers = _create_account(UserRole.ADMIN)
    user_email, user_headers = _create_account(UserRole.USER)
    test_id = None
    try:
        created = client.post(
            "/api/v1/tests",
            json={"name": f"Locked Test {uuid.uuid4()}", "description": "Panel"},
            headers=admin_headers,
        )
        assert created.status_code == 201
        test_id = created.json()["id"]
        updated = client.put(
            f"/api/v1/tests/{test_id}",
            json={"name": "Renamed", "description": "Panel"},
            headers=user_headers,
        )
        assert updated.status_code == 403
        deleted = client.delete(f"/api/v1/tests/{test_id}", headers=user_headers)
        assert deleted.status_code == 403
        extra = client.post(
            "/api/v1/tests",
            json={"name": "Extra", "description": "Panel", "price": 10},
            headers=admin_headers,
        )
        assert extra.status_code == 422
    finally:
        if test_id is not None:
            _delete_test(test_id)
        _delete_account(user_email)
        _delete_account(admin_email)


def test_test_pagination_limit_is_capped() -> None:
    email, headers = _create_account(UserRole.USER)
    try:
        response = client.get("/api/v1/tests?page=1&limit=500", headers=headers)
        assert response.status_code == 422
    finally:
        _delete_account(email)
