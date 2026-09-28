from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

_password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return _password_hash.verify(plain_password, hashed_password)
    except UnknownHashError:
        return False
