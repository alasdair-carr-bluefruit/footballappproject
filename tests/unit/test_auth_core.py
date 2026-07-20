"""Unit tests for the auth core: token hashing, session signing, expiry."""
import pytest

from backend.auth import session as session_mod
from backend.auth.tokens import (
    hash_token,
    is_expired,
    iso_in,
    new_token,
    tokens_match,
)

pytestmark = pytest.mark.unit


def test_new_token_is_unique_and_hidden_by_hash():
    a, b = new_token(), new_token()
    assert a != b
    assert hash_token(a) != a  # the stored form is not the raw token
    assert hash_token(a) == hash_token(a)  # deterministic


def test_tokens_match_only_for_the_right_raw():
    raw = new_token()
    stored = hash_token(raw)
    assert tokens_match(raw, stored)
    assert not tokens_match(new_token(), stored)


def test_is_expired():
    assert not is_expired(iso_in(minutes=15))
    assert is_expired(iso_in(minutes=-1))
    assert is_expired("not-a-date")
    assert not is_expired("2999-01-01T00:00:00")  # naive iso (no tz) is treated as UTC


def test_session_sign_and_verify_roundtrip():
    token = session_mod.sign_session(42)
    assert session_mod.verify_session(token) == 42


def test_session_rejects_tampering_and_garbage():
    token = session_mod.sign_session(7)
    payload, sig = token.split(".", 1)
    assert session_mod.verify_session(f"{payload}.{sig}x") is None  # bad signature
    assert session_mod.verify_session("garbage") is None
    assert session_mod.verify_session("") is None
    assert session_mod.verify_session(None) is None


def test_session_rejects_wrong_secret(monkeypatch):
    token = session_mod.sign_session(9)
    monkeypatch.setenv("SECRET_KEY", "a-different-key-entirely")
    assert session_mod.verify_session(token) is None


def test_session_rejects_expired(monkeypatch):
    token = session_mod.sign_session(5)
    monkeypatch.setattr(session_mod, "SESSION_MAX_AGE_DAYS", -1)
    assert session_mod.verify_session(token) is None
