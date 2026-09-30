import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.main import app
from app.models.booking import Booking
from app.models.centre import DiagnosticCentre
from app.models.test import DiagnosticTest
from app.models.user import User, UserRole

client = TestClient(app)


def _create_account(role: UserRole, name: str) -> tuple[str, dict[str, str]]:
    email = f"{uuid.uuid4()}@example.com"
    db = SessionLocal()
    try:
        db.add(User(name=name, email=email, password_hash=hash_password("StrongPassword123"), role=role))
        db.commit()
    finally:
        db.close()
    response = client.post("/api/v1/auth/login", json={"email": email, "password": "StrongPassword123"})
    assert response.status_code == 200
    return email, {"Authorization": f"Bearer {response.json()['access_token']}"}


def _cleanup(emails: list[str], centre_id: str | None, test_id: str | None) -> None:
    db = SessionLocal()
    try:
        if centre_id is not None:
            db.execute(delete(Booking).where(Booking.centre_id == uuid.UUID(centre_id)))
        if test_id is not None:
            db.execute(delete(Booking).where(Booking.test_id == uuid.UUID(test_id)))
        for email in emails:
            user = db.scalar(select(User).where(User.email == email))
            if user is not None:
                db.execute(delete(Booking).where(Booking.user_id == user.id))
                db.delete(user)
        if centre_id is not None:
            centre = db.get(DiagnosticCentre, uuid.UUID(centre_id))
            if centre is not None:
                db.delete(centre)
        if test_id is not None:
            diagnostic_test = db.get(DiagnosticTest, uuid.UUID(test_id))
            if diagnostic_test is not None:
                db.delete(diagnostic_test)
        db.commit()
    finally:
        db.close()


def _offer(admin_headers: dict[str, str]) -> tuple[str, str]:
    centre = client.post(
        "/api/v1/centres",
        json={"name": f"Access Lab {uuid.uuid4()}", "location": "Pune"},
        headers=admin_headers,
    )
    diagnostic_test = client.post(
        "/api/v1/tests",
        json={"name": f"Access CBC {uuid.uuid4()}", "description": "Blood count"},
        headers=admin_headers,
    )
    assert centre.status_code == 201
    assert diagnostic_test.status_code == 201
    centre_id = centre.json()["id"]
    test_id = diagnostic_test.json()["id"]
    offering = client.post(
        f"/api/v1/centres/{centre_id}/tests",
        json={"test_id": test_id, "price": "500.00"},
        headers=admin_headers,
    )
    assert offering.status_code == 201
    return centre_id, test_id


def _book(headers: dict[str, str], centre_id: str, test_id: str, when: str) -> str:
    response = client.post(
        "/api/v1/bookings",
        json={"centre_id": centre_id, "test_id": test_id, "appointment_at": when},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_users_see_only_their_bookings_and_admin_sees_all() -> None:
    admin_email, admin_headers = _create_account(UserRole.ADMIN, "Admin")
    first_email, first_headers = _create_account(UserRole.USER, "First")
    second_email, second_headers = _create_account(UserRole.USER, "Second")
    centre_id = None
    test_id = None
    try:
        centre_id, test_id = _offer(admin_headers)
        first_booking = _book(first_headers, centre_id, test_id, "2027-11-15T10:00:00")
        second_booking = _book(second_headers, centre_id, test_id, "2027-11-16T10:00:00")

        own = client.get("/api/v1/bookings?page=1&limit=20", headers=first_headers)
        assert own.status_code == 200
        body = own.json()
        assert body["page"] == 1
        assert body["limit"] == 20
        assert body["total"] == 1
        assert [item["id"] for item in body["items"]] == [first_booking]

        hidden = client.get(f"/api/v1/bookings/{second_booking}", headers=first_headers)
        assert hidden.status_code == 403

        visible = client.get(f"/api/v1/bookings/{first_booking}", headers=first_headers)
        assert visible.status_code == 200
        assert visible.json()["id"] == first_booking

        admin_one = client.get(f"/api/v1/bookings/{second_booking}", headers=admin_headers)
        assert admin_one.status_code == 200
        admin_list = client.get("/api/v1/bookings?page=1&limit=100", headers=admin_headers)
        assert admin_list.status_code == 200
        admin_ids = {item["id"] for item in admin_list.json()["items"]}
        assert first_booking in admin_ids
        assert second_booking in admin_ids
    finally:
        _cleanup([admin_email, first_email, second_email], centre_id, test_id)


def test_missing_booking_returns_not_found() -> None:
    email, headers = _create_account(UserRole.USER, "Reader")
    try:
        response = client.get(f"/api/v1/bookings/{uuid.uuid4()}", headers=headers)
        assert response.status_code == 404
        assert response.json()["detail"] == "Booking not found"
    finally:
        _cleanup([email], None, None)


def test_booking_list_requires_authentication_and_caps_limit() -> None:
    response = client.get("/api/v1/bookings")
    assert response.status_code == 401
    email, headers = _create_account(UserRole.USER, "Pager")
    try:
        capped = client.get("/api/v1/bookings?page=1&limit=500", headers=headers)
        assert capped.status_code == 422
    finally:
        _cleanup([email], None, None)
