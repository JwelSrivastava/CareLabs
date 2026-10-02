import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.payment import PaymentCreate, PaymentPublic, PaymentWebhookRequest
from app.services.booking_service import BookingAccessError, BookingNotFoundError
from app.services.payment_service import (
    BookingNotPayableError,
    PaymentAccessError,
    PaymentAlreadyExistsError,
    PaymentNotFoundError,
    PaymentWebhookConflictError,
    apply_payment_webhook,
    get_payment,
    pay_for_booking,
)

router = APIRouter(prefix="/api/v1/payments", tags=["Payments"])


@router.post("", response_model=PaymentPublic, status_code=status.HTTP_201_CREATED, summary="Pay for a booking")
def create_payment(
    payload: PaymentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaymentPublic:
    try:
        payment = pay_for_booking(db, current_user, payload.booking_id)
    except BookingNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found") from None
    except BookingAccessError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot pay for this booking") from None
    except BookingNotPayableError as exc:
        detail = (
            "Cancelled bookings cannot be paid"
            if exc.reason == "cancelled"
            else "Only pending bookings can be paid"
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from None
    except PaymentAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A payment already exists for this booking",
        ) from None
    return PaymentPublic.model_validate(payment)


@router.post("/webhook", response_model=PaymentPublic, summary="Receive a payment provider result")
def receive_payment_webhook(
    payload: PaymentWebhookRequest,
    db: Session = Depends(get_db),
) -> PaymentPublic:
    try:
        payment = apply_payment_webhook(
            db,
            payload.payment_reference,
            payload.status,
            payload.provider_transaction_id,
        )
    except PaymentNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found") from None
    except BookingNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found") from None
    except PaymentWebhookConflictError as exc:
        detail = (
            "A successful payment cannot be marked as failed"
            if exc.reason == "success_locked"
            else "Cancelled bookings cannot be updated by a payment webhook"
            if exc.reason == "cancelled"
            else "Payment could not be updated"
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from None
    return PaymentPublic.model_validate(payment)


@router.get("/{payment_id}", response_model=PaymentPublic, summary="Get a payment")
def get_user_payment(
    payment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaymentPublic:
    try:
        payment = get_payment(db, current_user, payment_id)
    except PaymentNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found") from None
    except PaymentAccessError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot access this payment") from None
    return PaymentPublic.model_validate(payment)
