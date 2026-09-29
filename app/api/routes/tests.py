import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.database import get_db
from app.models.user import User
from app.schemas.common import Page
from app.schemas.test import TestPublic, TestWrite
from app.services.test_service import (
    TestAlreadyExistsError,
    TestNotFoundError,
    create_test,
    delete_test,
    get_test,
    list_tests,
    update_test,
)

router = APIRouter(prefix="/api/v1/tests", tags=["Diagnostic Tests"])


@router.get("", response_model=Page[TestPublic], summary="List diagnostic tests")
def list_diagnostic_tests(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Page[TestPublic]:
    items, total = list_tests(db, page, limit)
    return Page(items=items, page=page, limit=limit, total=total)


@router.get("/{test_id}", response_model=TestPublic, summary="Get a diagnostic test")
def get_diagnostic_test(
    test_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> TestPublic:
    try:
        diagnostic_test = get_test(db, test_id)
    except TestNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test not found") from None
    return TestPublic.model_validate(diagnostic_test)


@router.post("", response_model=TestPublic, status_code=status.HTTP_201_CREATED, summary="Create a diagnostic test")
def create_diagnostic_test(
    payload: TestWrite,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> TestPublic:
    try:
        diagnostic_test = create_test(db, payload)
    except TestAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A test with this name already exists",
        ) from None
    return TestPublic.model_validate(diagnostic_test)


@router.put("/{test_id}", response_model=TestPublic, summary="Update a diagnostic test")
def update_diagnostic_test(
    test_id: uuid.UUID,
    payload: TestWrite,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> TestPublic:
    try:
        diagnostic_test = update_test(db, test_id, payload)
    except TestNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test not found") from None
    except TestAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A test with this name already exists",
        ) from None
    return TestPublic.model_validate(diagnostic_test)


@router.delete("/{test_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a diagnostic test")
def delete_diagnostic_test(
    test_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> None:
    try:
        delete_test(db, test_id)
    except TestNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test not found") from None
