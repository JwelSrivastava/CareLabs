import uuid
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.main import app
from app.models.centre import DiagnosticCentre
from app.models.test import DiagnosticTest
from app.models.user import User, UserRole

client = TestClient(app)


def _create_account(role: UserRole) -> tuple[str, dict[str, str]]:
    email = f"{uuid.uuid4()}@example.com"
    db = SessionLocal()
    try:
        db.add(
            User(
                name="Offer Admin" if role == UserRole.ADMIN else "Offer User",
                email=email,
                password_hash=hash_password("StrongPassword123"),
                role=role,
            )
        )
        db.commit()
    finally:
        db.close()
    response = client.post("/api/v1/auth/login", json={"email": email, "password": "StrongPassword123"})
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


def _delete_centre(centre_id: str | None) -> None:
    if centre_id is None:
        return
    db = SessionLocal()
    try:
        centre = db.get(DiagnosticCentre, uuid.UUID(centre_id))
        if centre is not None:
            db.delete(centre)
            db.commit()
    finally:
        db.close()


def _delete_test(test_id: str | None) -> None:
    if test_id is None:
        return
    db = SessionLocal()
    try:
        diagnostic_test = db.get(DiagnosticTest, uuid.UUID(test_id))
        if diagnostic_test is not None:
            db.delete(diagnostic_test)
            db.commit()
    finally:
        db.close()


def _create_centre_and_test(headers: dict[str, str]) -> tuple[str, str]:
    centre = client.post(
        "/api/v1/centres",
        json={"name": f"Offer Lab {uuid.uuid4()}", "location": "Pune"},
        headers=headers,
    )
    assert centre.status_code == 201
    diagnostic_test = client.post(
        "/api/v1/tests",
        json={"name": f"CBC {uuid.uuid4()}", "description": "Blood count"},
        headers=headers,
    )
    assert diagnostic_test.status_code == 201
    return centre.json()["id"], diagnostic_test.json()["id"]


def test_admin_adds_test_and_user_can_list_it() -> None:
    admin_email, admin_headers = _create_account(UserRole.ADMIN)
    user_email, user_headers = _create_account(UserRole.USER)
    centre_id = None
    test_id = None
    try:
        centre_id, test_id = _create_centre_and_test(admin_headers)
        created = client.post(
            f"/api/v1/centres/{centre_id}/tests",
            json={"test_id": test_id, "price": "750.00"},
            headers=admin_headers,
        )
        assert created.status_code == 201
        body = created.json()
        assert body["centre_id"] == centre_id
        assert body["test_id"] == test_id
        assert Decimal(str(body["price"])) == Decimal("750.00")

        listing = client.get(f"/api/v1/centres/{centre_id}/tests", headers=user_headers)
        assert listing.status_code == 200
        items = listing.json()
        assert len(items) == 1
        assert items[0]["test_id"] == test_id
        assert Decimal(str(items[0]["price"])) == Decimal("750.00")
    finally:
        _delete_centre(centre_id)
        _delete_test(test_id)
        _delete_account(admin_email)
        _delete_account(user_email)


def test_normal_user_cannot_add_test_to_centre() -> None:
    admin_email, admin_headers = _create_account(UserRole.ADMIN)
    user_email, user_headers = _create_account(UserRole.USER)
    centre_id = None
    test_id = None
    try:
        centre_id, test_id = _create_centre_and_test(admin_headers)
        response = client.post(
            f"/api/v1/centres/{centre_id}/tests",
            json={"test_id": test_id, "price": 750},
            headers=user_headers,
        )
        assert response.status_code == 403
    finally:
        _delete_centre(centre_id)
        _delete_test(test_id)
        _delete_account(admin_email)
        _delete_account(user_email)


def test_add_test_rejects_missing_centre_or_test() -> None:
    email, headers = _create_account(UserRole.ADMIN)
    centre_id = None
    test_id = None
    try:
        centre_id, test_id = _create_centre_and_test(headers)
        missing_centre = client.post(
            f"/api/v1/centres/{uuid.uuid4()}/tests",
            json={"test_id": test_id, "price": 750},
            headers=headers,
        )
        assert missing_centre.status_code == 404
        assert missing_centre.json()["detail"] == "Centre not found"

        missing_test = client.post(
            f"/api/v1/centres/{centre_id}/tests",
            json={"test_id": str(uuid.uuid4()), "price": 750},
            headers=headers,
        )
        assert missing_test.status_code == 404
        assert missing_test.json()["detail"] == "Test not found"
    finally:
        _delete_centre(centre_id)
        _delete_test(test_id)
        _delete_account(email)


def test_add_test_rejects_non_positive_price_and_duplicates() -> None:
    email, headers = _create_account(UserRole.ADMIN)
    centre_id = None
    test_id = None
    try:
        centre_id, test_id = _create_centre_and_test(headers)
        invalid = client.post(
            f"/api/v1/centres/{centre_id}/tests",
            json={"test_id": test_id, "price": 0},
            headers=headers,
        )
        assert invalid.status_code == 422

        created = client.post(
            f"/api/v1/centres/{centre_id}/tests",
            json={"test_id": test_id, "price": 750},
            headers=headers,
        )
        assert created.status_code == 201
        duplicate = client.post(
            f"/api/v1/centres/{centre_id}/tests",
            json={"test_id": test_id, "price": 800},
            headers=headers,
        )
        assert duplicate.status_code == 409
    finally:
        _delete_centre(centre_id)
        _delete_test(test_id)
        _delete_account(email)


def test_unknown_centre_offering_list_is_not_found() -> None:
    email, headers = _create_account(UserRole.USER)
    try:
        response = client.get(f"/api/v1/centres/{uuid.uuid4()}/tests", headers=headers)
        assert response.status_code == 404
    finally:
        _delete_account(email)
