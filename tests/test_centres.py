import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.main import app
from app.models.centre import DiagnosticCentre
from app.models.user import User, UserRole

client = TestClient(app)


def _create_account(role: UserRole) -> tuple[str, dict[str, str]]:
    email = f"{uuid.uuid4()}@example.com"
    db = SessionLocal()
    try:
        db.add(
            User(
                name="Centre Admin" if role == UserRole.ADMIN else "Centre User",
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


def _delete_centre(centre_id: str) -> None:
    db = SessionLocal()
    try:
        centre = db.get(DiagnosticCentre, uuid.UUID(centre_id))
        if centre is not None:
            db.delete(centre)
            db.commit()
    finally:
        db.close()


def test_admin_creates_centre_and_user_can_list_it() -> None:
    admin_email, admin_headers = _create_account(UserRole.ADMIN)
    user_email, user_headers = _create_account(UserRole.USER)
    centre_id = None
    name = f"City Lab {uuid.uuid4()}"
    try:
        created = client.post(
            "/api/v1/centres",
            json={"name": name, "location": "Pune"},
            headers=admin_headers,
        )
        assert created.status_code == 201
        centre_id = created.json()["id"]
        assert created.json()["name"] == name
        assert created.json()["location"] == "Pune"

        listing = client.get("/api/v1/centres?page=1&limit=100", headers=user_headers)
        assert listing.status_code == 200
        body = listing.json()
        assert body["page"] == 1
        assert body["limit"] == 100
        assert body["total"] >= 1
        assert any(item["id"] == centre_id for item in body["items"])

        fetched = client.get(f"/api/v1/centres/{centre_id}", headers=user_headers)
        assert fetched.status_code == 200
        assert fetched.json()["id"] == centre_id
    finally:
        if centre_id is not None:
            _delete_centre(centre_id)
        _delete_account(admin_email)
        _delete_account(user_email)


def test_normal_user_cannot_create_centre() -> None:
    email, headers = _create_account(UserRole.USER)
    try:
        response = client.post(
            "/api/v1/centres",
            json={"name": "Blocked Lab", "location": "Pune"},
            headers=headers,
        )
        assert response.status_code == 403
    finally:
        _delete_account(email)


def test_centre_not_found() -> None:
    email, headers = _create_account(UserRole.USER)
    try:
        response = client.get(f"/api/v1/centres/{uuid.uuid4()}", headers=headers)
        assert response.status_code == 404
        assert response.json()["detail"] == "Centre not found"
    finally:
        _delete_account(email)


def test_unauthenticated_centre_list_is_rejected() -> None:
    response = client.get("/api/v1/centres")
    assert response.status_code == 401


def test_duplicate_centre_name_and_location_conflicts() -> None:
    email, headers = _create_account(UserRole.ADMIN)
    name = f"Duplicate Lab {uuid.uuid4()}"
    centre_id = None
    try:
        first = client.post("/api/v1/centres", json={"name": name, "location": "Mumbai"}, headers=headers)
        assert first.status_code == 201
        centre_id = first.json()["id"]
        second = client.post("/api/v1/centres", json={"name": name, "location": "Mumbai"}, headers=headers)
        assert second.status_code == 409
    finally:
        if centre_id is not None:
            _delete_centre(centre_id)
        _delete_account(email)


def test_admin_can_update_and_delete_centre() -> None:
    email, headers = _create_account(UserRole.ADMIN)
    name = f"Editable Lab {uuid.uuid4()}"
    centre_id = None
    try:
        created = client.post("/api/v1/centres", json={"name": name, "location": "Delhi"}, headers=headers)
        assert created.status_code == 201
        centre_id = created.json()["id"]
        updated = client.put(
            f"/api/v1/centres/{centre_id}",
            json={"name": name, "location": "Noida"},
            headers=headers,
        )
        assert updated.status_code == 200
        assert updated.json()["location"] == "Noida"
        deleted = client.delete(f"/api/v1/centres/{centre_id}", headers=headers)
        assert deleted.status_code == 204
        missing = client.get(f"/api/v1/centres/{centre_id}", headers=headers)
        assert missing.status_code == 404
        centre_id = None
    finally:
        if centre_id is not None:
            _delete_centre(centre_id)
        _delete_account(email)


def test_same_name_is_allowed_in_a_different_location() -> None:
    email, headers = _create_account(UserRole.ADMIN)
    name = f"Shared Lab {uuid.uuid4()}"
    first_id = None
    second_id = None
    try:
        first = client.post("/api/v1/centres", json={"name": name, "location": "Mumbai"}, headers=headers)
        second = client.post("/api/v1/centres", json={"name": name, "location": "Pune"}, headers=headers)
        assert first.status_code == 201
        assert second.status_code == 201
        first_id = first.json()["id"]
        second_id = second.json()["id"]
        extra = client.post(
            "/api/v1/centres",
            json={"name": name, "location": "Goa", "phone": "000"},
            headers=headers,
        )
        assert extra.status_code == 422
    finally:
        if first_id is not None:
            _delete_centre(first_id)
        if second_id is not None:
            _delete_centre(second_id)
        _delete_account(email)


def test_normal_user_cannot_change_a_centre() -> None:
    admin_email, admin_headers = _create_account(UserRole.ADMIN)
    user_email, user_headers = _create_account(UserRole.USER)
    centre_id = None
    try:
        created = client.post(
            "/api/v1/centres",
            json={"name": f"Locked Lab {uuid.uuid4()}", "location": "Delhi"},
            headers=admin_headers,
        )
        assert created.status_code == 201
        centre_id = created.json()["id"]
        updated = client.put(
            f"/api/v1/centres/{centre_id}",
            json={"name": "Renamed", "location": "Delhi"},
            headers=user_headers,
        )
        assert updated.status_code == 403
        deleted = client.delete(f"/api/v1/centres/{centre_id}", headers=user_headers)
        assert deleted.status_code == 403
    finally:
        if centre_id is not None:
            _delete_centre(centre_id)
        _delete_account(user_email)
        _delete_account(admin_email)


def test_pagination_limit_is_capped() -> None:
    email, headers = _create_account(UserRole.USER)
    try:
        response = client.get("/api/v1/centres?page=1&limit=500", headers=headers)
        assert response.status_code == 422
        blank_page = client.get("/api/v1/centres?page=0&limit=0", headers=headers)
        assert blank_page.status_code == 422
    finally:
        _delete_account(email)
