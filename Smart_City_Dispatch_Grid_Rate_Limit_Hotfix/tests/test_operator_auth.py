import pytest

from smartcity.operator_auth import (
    DEFAULT_ITERATIONS,
    OPERATOR_SESSION_TTL_SECONDS,
    clear_operator_session,
    hash_operator_password,
    is_operator_auth_configured,
    maintain_operator_session,
    verify_operator_password,
)


def test_password_hash_round_trip_and_not_plaintext():
    password = "correct horse battery staple!"
    encoded = hash_operator_password(password)
    assert encoded.startswith("pbkdf2_sha256$")
    assert password not in encoded
    assert verify_operator_password(password, encoded)
    assert not verify_operator_password("not the password", encoded)


def test_password_hash_rejects_too_short_password():
    with pytest.raises(ValueError, match="at least"):
        hash_operator_password("short")


def test_password_hash_rejects_iterations_outside_safety_bounds():
    with pytest.raises(ValueError, match="iterations"):
        hash_operator_password("correct horse battery staple!", iterations=1)


def test_password_hash_rejects_excessively_long_password():
    with pytest.raises(ValueError, match="at most"):
        hash_operator_password("a" * 1025)


def test_verifier_rejects_excessively_long_input():
    encoded = hash_operator_password("correct horse battery staple!")
    assert not verify_operator_password("a" * 1025, encoded)


def test_verify_rejects_malformed_hash():
    assert not verify_operator_password("whatever", "plaintext-password")
    assert not verify_operator_password("whatever", "pbkdf2_sha256$999999999$abc$xyz")


def test_auth_not_configured_without_secret(monkeypatch):
    monkeypatch.setattr("smartcity.operator_auth.get_operator_password_hash", lambda: None)
    assert not is_operator_auth_configured()


def test_auth_configured_when_hash_is_valid(monkeypatch):
    encoded = hash_operator_password("correct horse battery staple!")
    monkeypatch.setattr("smartcity.operator_auth.get_operator_password_hash", lambda: encoded)
    assert is_operator_auth_configured()


def test_session_is_inactive_when_not_authenticated():
    state = {"operator_authenticated": False}
    assert not maintain_operator_session(state, now=1000)


def test_active_session_refreshes_last_activity():
    state = {"operator_authenticated": True, "operator_last_activity": 1000.0}
    assert maintain_operator_session(state, now=1100)
    assert state["operator_last_activity"] == 1100.0


def test_session_expires_after_inactivity_timeout():
    state = {
        "operator_authenticated": True,
        "operator_last_activity": 1000.0,
        "public_intake_result": {"kind": "success"},
    }
    assert not maintain_operator_session(state, now=1000 + OPERATOR_SESSION_TTL_SECONDS + 1)
    assert "operator_authenticated" not in state
    assert state["operator_session_expired"] is True
    assert state["public_intake_result"] == {"kind": "success"}


def test_manual_clear_does_not_clear_public_state():
    state = {"operator_authenticated": True, "operator_last_activity": 1000.0, "report_text": "draft"}
    clear_operator_session(state)
    assert "operator_authenticated" not in state
    assert state["report_text"] == "draft"
