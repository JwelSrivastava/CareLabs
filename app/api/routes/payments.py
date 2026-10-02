from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.payment import PaymentCreate, PaymentPublic
from app.services.booking_service import BookingAccessError, BookingNotFoundError
from app.services.payment_service import (
    BookingNotPayableError,
    PaymentAlreadyExistsError,
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
