import random
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.booking import Booking, BookingStatus
from app.models.payment import Payment, PaymentStatus
from app.models.user import User
from app.services.booking_service import BookingAccessError, BookingNotFoundError


class BookingNotPayableError(Exception):
    """Raised when the booking status does not allow payment."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class PaymentAlreadyExistsError(Exception):
    """Raised when the booking already has a payment."""


def simulate_payment_outcome() -> PaymentStatus:
    return random.choice([PaymentStatus.SUCCESS, PaymentStatus.FAILED])


def pay_for_booking(db: Session, user: User, booking_id: uuid.UUID) -> Payment:
    booking = db.scalar(select(Booking).where(Booking.id == booking_id).with_for_update())
    if booking is None:
        raise BookingNotFoundError
    if booking.user_id != user.id:
        raise BookingAccessError
    if booking.status == BookingStatus.CANCELLED:
        raise BookingNotPayableError("cancelled")
    if booking.status != BookingStatus.PENDING:
        raise BookingNotPayableError("not_pending")
    if _payment_exists(db, booking.id):
        raise PaymentAlreadyExistsError

    outcome = simulate_payment_outcome()
    payment = Payment(
        booking_id=booking.id,
        payment_reference=_reference("PAY"),
        provider_transaction_id=_reference("TXN"),
        amount=booking.amount,
        status=outcome,
    )
    booking.status = BookingStatus.CONFIRMED if outcome == PaymentStatus.SUCCESS else BookingStatus.FAILED
    db.add(payment)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise PaymentAlreadyExistsError from None
    db.refresh(payment)
    return payment


def _payment_exists(db: Session, booking_id: uuid.UUID) -> bool:
    existing = db.scalar(select(Payment.id).where(Payment.booking_id == booking_id))
    return existing is not None


def _reference(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"
