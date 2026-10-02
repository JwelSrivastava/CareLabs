import uuid
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.main import app
from app.models.booking import Booking
from app.models.centre import DiagnosticCentre
from app.models.payment import Payment, PaymentStatus
from app.models.test import DiagnosticTest
from app.models.user import User, UserRole
from app.services import payment_service

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
            booking_ids = list(db.scalars(select(Booking.id).where(Booking.centre_id == uuid.UUID(centre_id))))
            if booking_ids:
                db.execute(delete(Payment).where(Payment.booking_id.in_(booking_ids)))
            db.execute(delete(Booking).where(Booking.centre_id == uuid.UUID(centre_id)))
        for email in emails:
            user = db.scalar(select(User).where(User.email == email))
            if user is not None:
                booking_ids = list(db.scalars(select(Booking.id).where(Booking.user_id == user.id)))
                if booking_ids:
                    db.execute(delete(Payment).where(Payment.booking_id.in_(booking_ids)))
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
        json={"name": f"Pay Lab {uuid.uuid4()}", "location": "Pune"},
        headers=admin_headers,
    )
    diagnostic_test = client.post(
        "/api/v1/tests",
        json={"name": f"Pay CBC {uuid.uuid4()}", "description": "Blood count"},
        headers=admin_headers,
    )
    assert centre.status_code == 201
    assert diagnostic_test.status_code == 201
    centre_id = centre.json()["id"]
    test_id = diagnostic_test.json()["id"]
    offering = client.post(
        f"/api/v1/centres/{centre_id}/tests",
        json={"test_id": test_id, "price": "880.00"},
        headers=admin_headers,
    )
    assert offering.status_code == 201
    booking = client.post(
        "/api/v1/bookings",
        json={"centre_id": centre_id, "test_id": test_id, "appointment_at": "2027-12-15T11:00:00"},
        headers=user_headers,
    )
    assert booking.status_code == 201
    assert Decimal(str(booking.json()["amount"])) == Decimal("880.00")
    return centre_id, test_id, booking.json()["id"]


def _pay(headers: dict[str, str], booking_id: str, outcome: PaymentStatus):
    original = payment_service.simulate_payment_outcome
    payment_service.simulate_payment_outcome = lambda: outcome
    try:
        return client.post("/api/v1/payments", json={"booking_id": booking_id}, headers=headers)
    finally:
        payment_service.simulate_payment_outcome = original


def test_successful_payment_confirms_the_booking() -> None:
    admin_email, admin_headers = _create_account(UserRole.ADMIN, "Admin")
    user_email, user_headers = _create_account(UserRole.USER, "Payer")
    centre_id = None
    test_id = None
    try:
        centre_id, test_id, booking_id = _offer_and_book(admin_headers, user_headers)
        response = _pay(user_headers, booking_id, PaymentStatus.SUCCESS)
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "SUCCESS"
        assert body["booking_id"] == booking_id
        assert Decimal(str(body["amount"])) == Decimal("880.00")
        assert body["payment_reference"].startswith("PAY-")
        booking = client.get(f"/api/v1/bookings/{booking_id}", headers=user_headers)
        assert booking.json()["status"] == "CONFIRMED"
    finally:
        _cleanup([admin_email, user_email], centre_id, test_id)


def test_failed_payment_fails_the_booking() -> None:
    admin_email, admin_headers = _create_account(UserRole.ADMIN, "Admin")
    user_email, user_headers = _create_account(UserRole.USER, "Payer")
    centre_id = None
    test_id = None
    try:
        centre_id, test_id, booking_id = _offer_and_book(admin_headers, user_headers)
        response = _pay(user_headers, booking_id, PaymentStatus.FAILED)
        assert response.status_code == 201
        assert response.json()["status"] == "FAILED"
        booking = client.get(f"/api/v1/bookings/{booking_id}", headers=user_headers)
        assert booking.json()["status"] == "FAILED"
    finally:
        _cleanup([admin_email, user_email], centre_id, test_id)


def test_payment_rejects_invalid_cancelled_and_duplicate_bookings() -> None:
    admin_email, admin_headers = _create_account(UserRole.ADMIN, "Admin")
    user_email, user_headers = _create_account(UserRole.USER, "Payer")
    other_email, other_headers = _create_account(UserRole.USER, "Other")
    centre_id = None
    test_id = None
    try:
        missing = client.post(
            "/api/v1/payments",
            json={"booking_id": str(uuid.uuid4())},
            headers=user_headers,
        )
        assert missing.status_code == 404

        centre_id, test_id, booking_id = _offer_and_book(admin_headers, user_headers)
        cancelled = client.patch(f"/api/v1/bookings/{booking_id}/cancel", headers=user_headers)
        assert cancelled.status_code == 200
        denied = _pay(user_headers, booking_id, PaymentStatus.SUCCESS)
        assert denied.status_code == 409
        assert denied.json()["detail"] == "Cancelled bookings cannot be paid"

        centre_id_2, test_id_2, booking_id_2 = _offer_and_book(admin_headers, user_headers)
        first = _pay(user_headers, booking_id_2, PaymentStatus.SUCCESS)
        assert first.status_code == 201
        second = _pay(user_headers, booking_id_2, PaymentStatus.SUCCESS)
        assert second.status_code == 409
        stranger = client.post("/api/v1/payments", json={"booking_id": booking_id_2}, headers=other_headers)
        assert stranger.status_code == 403
    finally:
        _cleanup([admin_email, user_email, other_email], centre_id, test_id)
        if "centre_id_2" in locals():
            _cleanup([], centre_id_2, test_id_2)


def test_payment_requires_authentication() -> None:
    response = client.post("/api/v1/payments", json={"booking_id": str(uuid.uuid4())})
    assert response.status_code == 401
