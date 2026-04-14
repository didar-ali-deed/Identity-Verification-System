import uuid

import pytest

from app.utils.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_hash_and_verify_password():
    hashed = hash_password("TestPass123")
    assert verify_password("TestPass123", hashed)
    assert not verify_password("WrongPass", hashed)


def test_hash_is_not_plaintext():
    hashed = hash_password("TestPass123")
    assert hashed != "TestPass123"
    assert len(hashed) > 50


def test_access_token_roundtrip():
    user_id = uuid.uuid4()
    token = create_access_token(user_id, "user")
    payload = decode_token(token)
    assert payload is not None
    assert payload["sub"] == str(user_id)
    assert payload["role"] == "user"
    assert payload["type"] == "access"


def test_refresh_token_roundtrip():
    user_id = uuid.uuid4()
    token = create_refresh_token(user_id)
    payload = decode_token(token)
    assert payload is not None
    assert payload["sub"] == str(user_id)
    assert payload["type"] == "refresh"
    assert "jti" in payload


def test_invalid_token_returns_none():
    assert decode_token("invalid-token") is None
    assert decode_token("") is None
    assert decode_token("eyJ.broken.token") is None


def test_different_passwords_different_hashes():
    h1 = hash_password("Password1")
    h2 = hash_password("Password1")
    # bcrypt generates different hashes for same password (salt)
    assert h1 != h2
    assert verify_password("Password1", h1)
    assert verify_password("Password1", h2)


def test_access_token_contains_role():
    user_id = uuid.uuid4()
    admin_token = create_access_token(user_id, "admin")
    payload = decode_token(admin_token)
    assert payload["role"] == "admin"
