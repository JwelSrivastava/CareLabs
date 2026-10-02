import random
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models.booking import Booking, BookingStatus
from app.models.payment import Payment, PaymentStatus
from app.models.user import User, UserRole
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


class PaymentNotFoundError(Exception):
    """Raised when a payment id does not exist."""


class PaymentAccessError(Exception):
    """Raised when a user tries to read a payment for someone else's booking."""


class PaymentWebhookConflictError(Exception):
    """Raised when a webhook would make an illegal payment transition."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def get_payment(db: Session, user: User, payment_id: uuid.UUID) -> Payment:
    payment = db.scalar(select(Payment).options(joinedload(Payment.booking)).where(Payment.id == payment_id))
    if payment is None:
        raise PaymentNotFoundError
    if user.role != UserRole.ADMIN and payment.booking.user_id != user.id:
        raise PaymentAccessError
    return payment


def apply_payment_webhook(
    db: Session,
    payment_reference: str,
    outcome: PaymentStatus,
    provider_transaction_id: str,
) -> Payment:
    payment = db.scalar(select(Payment).where(Payment.payment_reference == payment_reference))
    if payment is None:
        raise PaymentNotFoundError

    booking = db.scalar(select(Booking).where(Booking.id == payment.booking_id).with_for_update())
    if booking is None:
        raise BookingNotFoundError
    payment = db.scalar(select(Payment).where(Payment.id == payment.id).with_for_update())
    if payment is None:
        raise PaymentNotFoundError

    if payment.status == outcome:
        return payment
    if payment.status == PaymentStatus.SUCCESS and outcome == PaymentStatus.FAILED:
        raise PaymentWebhookConflictError("success_locked")
    if booking.status == BookingStatus.CANCELLED:
        raise PaymentWebhookConflictError("cancelled")

    payment.status = outcome
    payment.provider_transaction_id = provider_transaction_id
    booking.status = BookingStatus.CONFIRMED if outcome == PaymentStatus.SUCCESS else BookingStatus.FAILED
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise PaymentWebhookConflictError("conflict") from None
    db.refresh(payment)
    return payment


def _payment_exists(db: Session, booking_id: uuid.UUID) -> bool:
    existing = db.scalar(select(Payment.id).where(Payment.booking_id == booking_id))
    return existing is not None


def _reference(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"
