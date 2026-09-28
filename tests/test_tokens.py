import uuid
from datetime import timedelta

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.core.database import SessionLocal
from app.core.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
)
from app.api.deps import get_current_user
from app.models.user import User


def test_create_and_decode_access_token() -> None:
    subject = str(uuid.uuid4())
    token = create_access_token(subject)

    assert decode_access_token(token) == subject
    assert token != subject
    assert token.count(".") == 2


def test_decode_access_token_rejects_expired_token() -> None:
    token = create_access_token(str(uuid.uuid4()), expires_delta=timedelta(seconds=-1))

    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_decode_access_token_rejects_tampered_token() -> None:
    token = create_access_token(str(uuid.uuid4()))
    tampered = token[:-2] + ("a" if token[-1] != "a" else "b")

    with pytest.raises(InvalidTokenError):
        decode_access_token(tampered)


def test_get_current_user_requires_a_token() -> None:
    db = SessionLocal()
    try:
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(credentials=None, db=db)
    finally:
        db.close()

    assert exc_info.value.status_code == 401


def test_get_current_user_loads_the_token_subject() -> None:
    db = SessionLocal()
    user = User(name="Token User", email=f"{uuid.uuid4()}@example.com", password_hash=hash_password("StrongPassword123"))
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(str(user.id))
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    try:
        current = get_current_user(credentials=credentials, db=db)
        assert current.id == user.id
        assert current.email == user.email
    finally:
        db.delete(user)
        db.commit()
        db.close()


def test_get_current_user_rejects_an_unknown_subject() -> None:
    db = SessionLocal()
    token = create_access_token(str(uuid.uuid4()))
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    try:
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(credentials=credentials, db=db)
    finally:
        db.close()

    assert exc_info.value.status_code == 401
