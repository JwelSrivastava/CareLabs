import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models.centre_test import CentreTest
from app.schemas.centre_test import CentreTestCreate, CentreTestPublic
from app.services.centre_service import CentreNotFoundError, get_centre
from app.services.test_service import TestNotFoundError, get_test


class CentreTestAlreadyExistsError(Exception):
    """Raised when a centre already offers the selected test."""


def list_centre_tests(db: Session, centre_id: uuid.UUID) -> list[CentreTestPublic]:
    get_centre(db, centre_id)
    rows = db.scalars(
        select(CentreTest)
        .options(joinedload(CentreTest.test))
        .where(CentreTest.centre_id == centre_id)
        .order_by(CentreTest.created_at, CentreTest.id)
    ).all()
    return [_to_public(row) for row in rows]


def add_centre_test(db: Session, centre_id: uuid.UUID, data: CentreTestCreate) -> CentreTestPublic:
    get_centre(db, centre_id)
    get_test(db, data.test_id)
    existing = db.scalar(
        select(CentreTest.id).where(
            CentreTest.centre_id == centre_id,
            CentreTest.test_id == data.test_id,
        )
    )
    if existing is not None:
        raise CentreTestAlreadyExistsError

    offering = CentreTest(centre_id=centre_id, test_id=data.test_id, price=data.price)
    db.add(offering)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise CentreTestAlreadyExistsError from None
    created = db.scalar(
        select(CentreTest).options(joinedload(CentreTest.test)).where(CentreTest.id == offering.id)
    )
    if created is None:
        raise CentreTestAlreadyExistsError
    return _to_public(created)


def _to_public(offering: CentreTest) -> CentreTestPublic:
    return CentreTestPublic(
        id=offering.id,
        centre_id=offering.centre_id,
        test_id=offering.test_id,
        test_name=offering.test.name,
        price=offering.price,
        created_at=offering.created_at,
    )
