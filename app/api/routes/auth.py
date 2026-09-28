from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.auth import SignupRequest, UserPublic
from app.services.auth_service import EmailAlreadyExistsError, register_user

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


@router.post(
    "/signup",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account",
)
def signup(payload: SignupRequest, db: Session = Depends(get_db)) -> UserPublic:
    try:
        user = register_user(db, payload)
    except EmailAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered",
        ) from None
    return UserPublic.model_validate(user)
