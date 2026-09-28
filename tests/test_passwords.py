from app.core.security import hash_password, verify_password


def test_hash_password_does_not_store_plaintext() -> None:
    password = "StrongPassword123"
    hashed = hash_password(password)

    assert hashed != password
    assert password not in hashed
    assert hashed.startswith("$argon2id$")
    assert len(hashed) <= 255


def test_verify_password_accepts_matching_password() -> None:
    password = "StrongPassword123"
    hashed = hash_password(password)

    assert verify_password(password, hashed) is True


def test_verify_password_rejects_wrong_password() -> None:
    hashed = hash_password("StrongPassword123")

    assert verify_password("WrongPassword123", hashed) is False


def test_hash_password_uses_a_unique_salt() -> None:
    password = "StrongPassword123"

    assert hash_password(password) != hash_password(password)


def test_verify_password_rejects_unknown_hash() -> None:
    assert verify_password("StrongPassword123", "not-a-password-hash") is False
