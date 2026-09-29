import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.database import get_db
from app.models.user import User
from app.schemas.centre import CentrePublic, CentreWrite
from app.schemas.centre_test import CentreTestCreate, CentreTestPublic
from app.schemas.common import Page
from app.services.centre_test_service import (
    CentreTestAlreadyExistsError,
    add_centre_test,
    list_centre_tests,
)
from app.services.test_service import TestNotFoundError
from app.services.centre_service import (
    CentreAlreadyExistsError,
    CentreNotFoundError,
    create_centre,
    delete_centre,
    get_centre,
    list_centres,
    update_centre,
)

router = APIRouter(prefix="/api/v1/centres", tags=["Diagnostic Centres"])


@router.get("", response_model=Page[CentrePublic], summary="List diagnostic centres")
def list_diagnostic_centres(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Page[CentrePublic]:
    items, total = list_centres(db, page, limit)
    return Page(items=items, page=page, limit=limit, total=total)


@router.get("/{centre_id}", response_model=CentrePublic, summary="Get a diagnostic centre")
def get_diagnostic_centre(
    centre_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> CentrePublic:
    try:
        centre = get_centre(db, centre_id)
    except CentreNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Centre not found") from None
    return CentrePublic.model_validate(centre)


@router.post("", response_model=CentrePublic, status_code=status.HTTP_201_CREATED, summary="Create a diagnostic centre")
def create_diagnostic_centre(
    payload: CentreWrite,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> CentrePublic:
    try:
        centre = create_centre(db, payload)
    except CentreAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A centre with this name and location already exists",
        ) from None
    return CentrePublic.model_validate(centre)


@router.put("/{centre_id}", response_model=CentrePublic, summary="Update a diagnostic centre")
def update_diagnostic_centre(
    centre_id: uuid.UUID,
    payload: CentreWrite,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> CentrePublic:
    try:
        centre = update_centre(db, centre_id, payload)
    except CentreNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Centre not found") from None
    except CentreAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A centre with this name and location already exists",
        ) from None
    return CentrePublic.model_validate(centre)


@router.delete("/{centre_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a diagnostic centre")
def delete_diagnostic_centre(
    centre_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> None:
    try:
        delete_centre(db, centre_id)
    except CentreNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Centre not found") from None


@router.get("/{centre_id}/tests", response_model=list[CentreTestPublic], summary="List tests offered by a centre")
def list_offered_tests(
    centre_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[CentreTestPublic]:
    try:
        return list_centre_tests(db, centre_id)
    except CentreNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Centre not found") from None


@router.post(
    "/{centre_id}/tests",
    response_model=CentreTestPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Add a test to a centre",
)
def add_offered_test(
    centre_id: uuid.UUID,
    payload: CentreTestCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> CentreTestPublic:
    try:
        return add_centre_test(db, centre_id, payload)
    except CentreNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Centre not found") from None
    except TestNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test not found") from None
    except CentreTestAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This centre already offers the selected test",
        ) from None
