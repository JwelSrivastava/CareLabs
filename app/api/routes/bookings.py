import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.booking import BookingCreate, BookingPublic
from app.schemas.common import Page
from app.services.booking_service import (
    ActiveBookingExistsError,
    AppointmentInPastError,
    BookingAccessError,
    BookingNotFoundError,
    CentreDoesNotOfferTestError,
    create_booking,
    get_booking,
    list_bookings,
)
from app.services.centre_service import CentreNotFoundError
from app.services.test_service import TestNotFoundError

router = APIRouter(prefix="/api/v1/bookings", tags=["Bookings"])


@router.post("", response_model=BookingPublic, status_code=status.HTTP_201_CREATED, summary="Create a booking")
def create_user_booking(
    payload: BookingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BookingPublic:
    try:
        booking = create_booking(db, current_user, payload)
    except CentreNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Centre not found") from None
    except TestNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test not found") from None
    except CentreDoesNotOfferTestError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This centre does not offer the selected test",
        ) from None
    except AppointmentInPastError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Appointment time must be in the future",
        ) from None
    except ActiveBookingExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active booking already exists for this centre, test, and appointment",
        ) from None
    return BookingPublic.model_validate(booking)


@router.get("", response_model=Page[BookingPublic], summary="List bookings")
def list_user_bookings(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Page[BookingPublic]:
    items, total = list_bookings(db, current_user, page, limit)
    return Page(items=items, page=page, limit=limit, total=total)


@router.get("/{booking_id}", response_model=BookingPublic, summary="Get a booking")
def get_user_booking(
    booking_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BookingPublic:
    try:
        booking = get_booking(db, current_user, booking_id)
    except BookingNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found") from None
    except BookingAccessError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot access this booking") from None
    return BookingPublic.model_validate(booking)
