import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.main import app
from app.models.booking import Booking
from app.models.centre import DiagnosticCentre
from app.models.test import DiagnosticTest
from app.models.user import User, UserRole

client = TestClient(app)
FUTURE = "2027-10-15T10:00:00"
PAST = "2020-01-01T10:00:00"


def _create_account(role: UserRole) -> tuple[str, dict[str, str]]:
    email = f"{uuid.uuid4()}@example.com"
    db = SessionLocal()
    try:
        db.add(
            User(
                name="Booking Admin" if role == UserRole.ADMIN else "Booking User",
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
        if user is None:
            return
        db.query(Booking).filter(Booking.user_id == user.id).delete()
        db.delete(user)
        db.commit()
    finally:
        db.close()


def _delete_centre(centre_id: str | None) -> None:
    if centre_id is None:
        return
    db = SessionLocal()
    try:
        db.query(Booking).filter(Booking.centre_id == uuid.UUID(centre_id)).delete()
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
        db.query(Booking).filter(Booking.test_id == uuid.UUID(test_id)).delete()
        diagnostic_test = db.get(DiagnosticTest, uuid.UUID(test_id))
        if diagnostic_test is not None:
            db.delete(diagnostic_test)
        db.commit()
    finally:
        db.close()


def _offer(admin_headers: dict[str, str], price: str = "750.00") -> tuple[str, str]:
    centre = client.post(
        "/api/v1/centres",
        json={"name": f"Book Lab {uuid.uuid4()}", "location": "Pune"},
        headers=admin_headers,
    )
    assert centre.status_code == 201
    diagnostic_test = client.post(
        "/api/v1/tests",
        json={"name": f"Book CBC {uuid.uuid4()}", "description": "Blood count"},
        headers=admin_headers,
    )
    assert diagnostic_test.status_code == 201
    centre_id = centre.json()["id"]
    test_id = diagnostic_test.json()["id"]
    offering = client.post(
        f"/api/v1/centres/{centre_id}/tests",
        json={"test_id": test_id, "price": price},
        headers=admin_headers,
    )
    assert offering.status_code == 201
    return centre_id, test_id


def test_booking_uses_centre_price_and_ignores_client_amount() -> None:
    admin_email, admin_headers = _create_account(UserRole.ADMIN)
    user_email, user_headers = _create_account(UserRole.USER)
    centre_id = None
    test_id = None
    try:
        centre_id, test_id = _offer(admin_headers, "750.00")
        response = client.post(
            "/api/v1/bookings",
            json={
                "centre_id": centre_id,
                "test_id": test_id,
                "appointment_at": FUTURE,
                "amount": 1,
            },
            headers=user_headers,
        )
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "PENDING"
        assert Decimal(str(body["amount"])) == Decimal("750.00")
        assert body["user_id"]
    finally:
        _delete_centre(centre_id)
        _delete_test(test_id)
        _delete_account(user_email)
        _delete_account(admin_email)


def test_unauthenticated_booking_is_rejected() -> None:
    response = client.post(
        "/api/v1/bookings",
        json={"centre_id": str(uuid.uuid4()), "test_id": str(uuid.uuid4()), "appointment_at": FUTURE},
    )
    assert response.status_code == 401


def test_booking_requires_the_centre_to_offer_the_test() -> None:
    admin_email, admin_headers = _create_account(UserRole.ADMIN)
    user_email, user_headers = _create_account(UserRole.USER)
    centre_id = None
    test_id = None
    try:
        centre = client.post(
            "/api/v1/centres",
            json={"name": f"No Offer {uuid.uuid4()}", "location": "Pune"},
            headers=admin_headers,
        )
        diagnostic_test = client.post(
            "/api/v1/tests",
            json={"name": f"No Offer Test {uuid.uuid4()}", "description": "Not offered"},
            headers=admin_headers,
        )
        assert centre.status_code == 201
        assert diagnostic_test.status_code == 201
        centre_id = centre.json()["id"]
        test_id = diagnostic_test.json()["id"]
        response = client.post(
            "/api/v1/bookings",
            json={"centre_id": centre_id, "test_id": test_id, "appointment_at": FUTURE},
            headers=user_headers,
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "This centre does not offer the selected test"
    finally:
        _delete_centre(centre_id)
        _delete_test(test_id)
        _delete_account(user_email)
        _delete_account(admin_email)


def test_past_appointment_is_rejected() -> None:
    admin_email, admin_headers = _create_account(UserRole.ADMIN)
    user_email, user_headers = _create_account(UserRole.USER)
    centre_id = None
    test_id = None
    try:
        centre_id, test_id = _offer(admin_headers)
        response = client.post(
            "/api/v1/bookings",
            json={"centre_id": centre_id, "test_id": test_id, "appointment_at": PAST},
            headers=user_headers,
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Appointment time must be in the future"
    finally:
        _delete_centre(centre_id)
        _delete_test(test_id)
        _delete_account(user_email)
        _delete_account(admin_email)


def test_appointments_are_stored_in_utc() -> None:
    admin_email, admin_headers = _create_account(UserRole.ADMIN)
    user_email, user_headers = _create_account(UserRole.USER)
    centre_id = None
    test_id = None
    try:
        centre_id, test_id = _offer(admin_headers)
        naive = client.post(
            "/api/v1/bookings",
            json={"centre_id": centre_id, "test_id": test_id, "appointment_at": "2027-10-15T10:00:00"},
            headers=user_headers,
        )
        assert naive.status_code == 201
        naive_at = datetime.fromisoformat(naive.json()["appointment_at"])
        assert naive_at.astimezone(timezone.utc) == datetime(2027, 10, 15, 10, 0, tzinfo=timezone.utc)

        shifted = client.post(
            "/api/v1/bookings",
            json={"centre_id": centre_id, "test_id": test_id, "appointment_at": "2027-10-16T15:30:00+05:30"},
            headers=user_headers,
        )
        assert shifted.status_code == 201
        shifted_at = datetime.fromisoformat(shifted.json()["appointment_at"])
        assert shifted_at.astimezone(timezone.utc) == datetime(2027, 10, 16, 10, 0, tzinfo=timezone.utc)
    finally:
        _delete_centre(centre_id)
        _delete_test(test_id)
        _delete_account(user_email)
        _delete_account(admin_email)


def test_missing_centre_or_test_is_not_found() -> None:
    admin_email, admin_headers = _create_account(UserRole.ADMIN)
    user_email, user_headers = _create_account(UserRole.USER)
    centre_id = None
    test_id = None
    try:
        centre_id, test_id = _offer(admin_headers)
        missing_centre = client.post(
            "/api/v1/bookings",
            json={"centre_id": str(uuid.uuid4()), "test_id": test_id, "appointment_at": FUTURE},
            headers=user_headers,
        )
        assert missing_centre.status_code == 404
        assert missing_centre.json()["detail"] == "Centre not found"

        missing_test = client.post(
            "/api/v1/bookings",
            json={"centre_id": centre_id, "test_id": str(uuid.uuid4()), "appointment_at": FUTURE},
            headers=user_headers,
        )
        assert missing_test.status_code == 404
        assert missing_test.json()["detail"] == "Test not found"

        extra = client.post(
            "/api/v1/bookings",
            json={"centre_id": centre_id, "test_id": test_id, "appointment_at": FUTURE, "note": "rush"},
            headers=user_headers,
        )
        assert extra.status_code == 422
    finally:
        _delete_centre(centre_id)
        _delete_test(test_id)
        _delete_account(user_email)
        _delete_account(admin_email)


def test_duplicate_active_booking_conflicts() -> None:
    admin_email, admin_headers = _create_account(UserRole.ADMIN)
    user_email, user_headers = _create_account(UserRole.USER)
    centre_id = None
    test_id = None
    try:
        centre_id, test_id = _offer(admin_headers)
        payload = {"centre_id": centre_id, "test_id": test_id, "appointment_at": FUTURE}
        first = client.post("/api/v1/bookings", json=payload, headers=user_headers)
        assert first.status_code == 201
        second = client.post("/api/v1/bookings", json=payload, headers=user_headers)
        assert second.status_code == 409
    finally:
        _delete_centre(centre_id)
        _delete_test(test_id)
        _delete_account(user_email)
        _delete_account(admin_email)
