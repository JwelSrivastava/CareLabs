import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.test import DiagnosticTest
from app.schemas.test import TestWrite


class TestNotFoundError(Exception):
    """Raised when a diagnostic test id does not exist."""


class TestAlreadyExistsError(Exception):
    """Raised when a diagnostic test name is already in the catalog."""


def list_tests(db: Session, page: int, limit: int) -> tuple[list[DiagnosticTest], int]:
    total = db.scalar(select(func.count()).select_from(DiagnosticTest)) or 0
    items = db.scalars(
        select(DiagnosticTest)
        .order_by(DiagnosticTest.name, DiagnosticTest.id)
        .offset((page - 1) * limit)
        .limit(limit)
    ).all()
    return list(items), total


def get_test(db: Session, test_id: uuid.UUID) -> DiagnosticTest:
    diagnostic_test = db.get(DiagnosticTest, test_id)
    if diagnostic_test is None:
        raise TestNotFoundError(str(test_id))
    return diagnostic_test


def create_test(db: Session, data: TestWrite) -> DiagnosticTest:
    diagnostic_test = DiagnosticTest(name=data.name, description=data.description)
    db.add(diagnostic_test)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise TestAlreadyExistsError from None
    db.refresh(diagnostic_test)
    return diagnostic_test


def update_test(db: Session, test_id: uuid.UUID, data: TestWrite) -> DiagnosticTest:
    diagnostic_test = get_test(db, test_id)
    diagnostic_test.name = data.name
    diagnostic_test.description = data.description
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise TestAlreadyExistsError from None
    db.refresh(diagnostic_test)
    return diagnostic_test


def delete_test(db: Session, test_id: uuid.UUID) -> None:
    diagnostic_test = get_test(db, test_id)
    db.delete(diagnostic_test)
    db.commit()
