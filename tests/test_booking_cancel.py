import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.main import app
from app.models.booking import Booking, BookingStatus
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


def _offer_and_book(admin_headers: dict[str, str], user_headers: dict[str, str]) -> tuple[str, str, str]:
    centre = client.post(
        "/api/v1/centres",
        json={"name": f"Cancel Lab {uuid.uuid4()}", "location": "Pune"},
        headers=admin_headers,
    )
    diagnostic_test = client.post(
        "/api/v1/tests",
        json={"name": f"Cancel CBC {uuid.uuid4()}", "description": "Blood count"},
        headers=admin_headers,
    )
    assert centre.status_code == 201
    assert diagnostic_test.status_code == 201
    centre_id = centre.json()["id"]
    test_id = diagnostic_test.json()["id"]
    offering = client.post(
        f"/api/v1/centres/{centre_id}/tests",
        json={"test_id": test_id, "price": "640.00"},
        headers=admin_headers,
    )
    assert offering.status_code == 201
    booking = client.post(
        "/api/v1/bookings",
        json={"centre_id": centre_id, "test_id": test_id, "appointment_at": "2027-12-01T09:00:00"},
        headers=user_headers,
    )
    assert booking.status_code == 201
    return centre_id, test_id, booking.json()["id"]


def _set_status(booking_id: str, status: BookingStatus) -> None:
    db = SessionLocal()
    try:
        booking = db.get(Booking, uuid.UUID(booking_id))
        assert booking is not None
        booking.status = status
        db.commit()
    finally:
        db.close()


def test_owner_can_cancel_a_pending_booking() -> None:
    admin_email, admin_headers = _create_account(UserRole.ADMIN, "Admin")
    user_email, user_headers = _create_account(UserRole.USER, "Owner")
    centre_id = None
    test_id = None
    try:
        centre_id, test_id, booking_id = _offer_and_book(admin_headers, user_headers)
        response = client.patch(f"/api/v1/bookings/{booking_id}/cancel", headers=user_headers)
        assert response.status_code == 200
        assert response.json()["status"] == "CANCELLED"
        again = client.patch(f"/api/v1/bookings/{booking_id}/cancel", headers=user_headers)
        assert again.status_code == 409
    finally:
        _cleanup([admin_email, user_email], centre_id, test_id)


def test_other_user_cannot_cancel_and_admin_can() -> None:
    admin_email, admin_headers = _create_account(UserRole.ADMIN, "Admin")
    owner_email, owner_headers = _create_account(UserRole.USER, "Owner")
    other_email, other_headers = _create_account(UserRole.USER, "Other")
    centre_id = None
    test_id = None
    try:
        centre_id, test_id, booking_id = _offer_and_book(admin_headers, owner_headers)
        denied = client.patch(f"/api/v1/bookings/{booking_id}/cancel", headers=other_headers)
        assert denied.status_code == 403
        cancelled = client.patch(f"/api/v1/bookings/{booking_id}/cancel", headers=admin_headers)
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "CANCELLED"
    finally:
        _cleanup([admin_email, owner_email, other_email], centre_id, test_id)


def test_confirmed_booking_cannot_be_cancelled() -> None:
    admin_email, admin_headers = _create_account(UserRole.ADMIN, "Admin")
    user_email, user_headers = _create_account(UserRole.USER, "Owner")
    centre_id = None
    test_id = None
    try:
        centre_id, test_id, booking_id = _offer_and_book(admin_headers, user_headers)
        _set_status(booking_id, BookingStatus.CONFIRMED)
        response = client.patch(f"/api/v1/bookings/{booking_id}/cancel", headers=user_headers)
        assert response.status_code == 409
        assert response.json()["detail"] == "Only pending bookings can be cancelled"
    finally:
        _cleanup([admin_email, user_email], centre_id, test_id)


def test_cancel_requires_authentication_and_a_real_booking() -> None:
    missing = client.patch(f"/api/v1/bookings/{uuid.uuid4()}/cancel")
    assert missing.status_code == 401
    email, headers = _create_account(UserRole.USER, "Owner")
    try:
        response = client.patch(f"/api/v1/bookings/{uuid.uuid4()}/cancel", headers=headers)
        assert response.status_code == 404
    finally:
        _cleanup([email], None, None)
