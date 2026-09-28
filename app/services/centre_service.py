import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.centre import DiagnosticCentre
from app.schemas.centre import CentreWrite


class CentreNotFoundError(Exception):
    """Raised when a diagnostic centre id does not exist."""


class CentreAlreadyExistsError(Exception):
    """Raised when a centre with the same name and location already exists."""


def list_centres(db: Session, page: int, limit: int) -> tuple[list[DiagnosticCentre], int]:
    total = db.scalar(select(func.count()).select_from(DiagnosticCentre)) or 0
    items = db.scalars(
        select(DiagnosticCentre)
        .order_by(DiagnosticCentre.name, DiagnosticCentre.location, DiagnosticCentre.id)
        .offset((page - 1) * limit)
        .limit(limit)
    ).all()
    return list(items), total


def get_centre(db: Session, centre_id: uuid.UUID) -> DiagnosticCentre:
    centre = db.get(DiagnosticCentre, centre_id)
    if centre is None:
        raise CentreNotFoundError(str(centre_id))
    return centre


def create_centre(db: Session, data: CentreWrite) -> DiagnosticCentre:
    centre = DiagnosticCentre(name=data.name, location=data.location)
    db.add(centre)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise CentreAlreadyExistsError from None
    db.refresh(centre)
    return centre


def update_centre(db: Session, centre_id: uuid.UUID, data: CentreWrite) -> DiagnosticCentre:
    centre = get_centre(db, centre_id)
    centre.name = data.name
    centre.location = data.location
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise CentreAlreadyExistsError from None
    db.refresh(centre)
    return centre


def delete_centre(db: Session, centre_id: uuid.UUID) -> None:
    centre = get_centre(db, centre_id)
    db.delete(centre)
    db.commit()
