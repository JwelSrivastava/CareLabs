import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.booking import Booking, BookingStatus
from app.models.centre_test import CentreTest
from app.models.user import User, UserRole
from app.schemas.booking import BookingCreate
from app.services.centre_service import get_centre
from app.services.test_service import get_test


class CentreDoesNotOfferTestError(Exception):
    """Raised when the selected centre does not offer the selected test."""


class AppointmentInPastError(Exception):
    """Raised when the appointment is not in the future."""


class ActiveBookingExistsError(Exception):
    """Raised when the user already has an active booking for the same slot."""


def create_booking(db: Session, user: User, data: BookingCreate) -> Booking:
    get_centre(db, data.centre_id)
    get_test(db, data.test_id)
    offering = db.scalar(
        select(CentreTest).where(
            CentreTest.centre_id == data.centre_id,
            CentreTest.test_id == data.test_id,
        )
    )
    if offering is None:
        raise CentreDoesNotOfferTestError

    appointment_at = _as_utc(data.appointment_at)
    if appointment_at <= datetime.now(timezone.utc):
        raise AppointmentInPastError

    booking = Booking(
        user_id=user.id,
        centre_id=data.centre_id,
        test_id=data.test_id,
        appointment_at=appointment_at,
        amount=offering.price,
        status=BookingStatus.PENDING,
    )
    db.add(booking)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ActiveBookingExistsError from None
    db.refresh(booking)
    return booking


class BookingNotFoundError(Exception):
    """Raised when a booking id does not exist."""


class BookingAccessError(Exception):
    """Raised when a user tries to read another user's booking."""


def list_bookings(db: Session, user: User, page: int, limit: int) -> tuple[list[Booking], int]:
    filters = []
    if user.role != UserRole.ADMIN:
        filters.append(Booking.user_id == user.id)
    total = db.scalar(select(func.count()).select_from(Booking).where(*filters)) or 0
    items = db.scalars(
        select(Booking)
        .where(*filters)
        .order_by(Booking.appointment_at.desc(), Booking.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    ).all()
    return list(items), total


def get_booking(db: Session, user: User, booking_id: uuid.UUID) -> Booking:
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise BookingNotFoundError
    if user.role != UserRole.ADMIN and booking.user_id != user.id:
        raise BookingAccessError
    return booking


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
