from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.user import User, UserRole
from app.repositories.user_repository import get_user_by_email
from app.schemas.auth import SignupRequest


class EmailAlreadyExistsError(Exception):
    """Raised when signup uses an email that is already registered."""


def register_user(db: Session, data: SignupRequest) -> User:
    if get_user_by_email(db, data.email) is not None:
        raise EmailAlreadyExistsError(data.email)

    user = User(
        name=data.name,
        email=data.email,
        password_hash=hash_password(data.password),
        role=UserRole.USER,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise EmailAlreadyExistsError(data.email) from None
    db.refresh(user)
    return user
