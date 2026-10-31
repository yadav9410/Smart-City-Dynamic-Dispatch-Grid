import hashlib

import pytest

import smartcity.abuse_protection as protection
from smartcity.abuse_protection import (
    ACTION_POLICIES,
    public_limit_message,
    reserve_action_slot,
)


def test_session_rate_limit_allows_policy_quota_then_blocks(monkeypatch):
    monkeypatch.setattr(protection, "is_database_configured", lambda: False)
    state = {}
    policy = ACTION_POLICIES["report_submit"]
    decisions = [
        reserve_action_slot(state, "report_submit", now=1000 + i)
        for i in range(policy.max_requests)
    ]
    assert all(item.allowed for item in decisions)

    blocked = reserve_action_slot(state, "report_submit", now=1004)
    assert blocked.allowed is False
    assert blocked.reason == "session_rate_limit"
    assert 1 <= blocked.retry_after_seconds <= policy.window_seconds
    assert "wait" in public_limit_message(blocked).lower()


def test_session_rate_limit_resets_after_window(monkeypatch):
    monkeypatch.setattr(protection, "is_database_configured", lambda: False)
    state = {}
    policy = ACTION_POLICIES["audio_transcription"]
    for i in range(policy.max_requests):
        assert reserve_action_slot(state, "audio_transcription", now=100 + i).allowed
    blocked = reserve_action_slot(state, "audio_transcription", now=105)
    assert not blocked.allowed

    refreshed = reserve_action_slot(
        state, "audio_transcription", now=100 + policy.window_seconds + 10
    )
    assert refreshed.allowed


def test_actions_have_independent_quotas(monkeypatch):
    monkeypatch.setattr(protection, "is_database_configured", lambda: False)
    state = {}
    for i in range(ACTION_POLICIES["report_submit"].max_requests):
        assert reserve_action_slot(state, "report_submit", now=200 + i).allowed
    assert reserve_action_slot(state, "audio_transcription", now=205).allowed


def test_unknown_action_fails_closed():
    result = reserve_action_slot({}, "not_an_action", now=100)
    assert not result.allowed
    assert result.reason == "unsupported_action"


def test_database_limiter_uses_hashed_server_session_token(monkeypatch):
    captured = {}
    monkeypatch.setattr(protection, "is_database_configured", lambda: True)

    def fake_consume(**kwargs):
        captured.update(kwargs)
        return {"allowed": True, "remaining": 2, "retry_after_seconds": 500}

    monkeypatch.setattr(protection, "consume_persistent_rate_limit", fake_consume)
    state = {}
    decision = reserve_action_slot(state, "report_submit", now=100)

    raw_token = state["_abuse_protection_session_nonce"]
    assert decision.allowed
    assert decision.persistent
    assert captured["session_hash"] == hashlib.sha256(raw_token.encode()).hexdigest()
    assert captured["session_hash"] != raw_token
    assert len(captured["session_hash"]) == 64


def test_database_limiter_blocks_when_persistent_quota_exceeded(monkeypatch):
    monkeypatch.setattr(protection, "is_database_configured", lambda: True)
    monkeypatch.setattr(
        protection,
        "consume_persistent_rate_limit",
        lambda **kwargs: {"allowed": False, "remaining": 0, "retry_after_seconds": 44},
    )
    result = reserve_action_slot({}, "ai_assessment", now=100)
    assert not result.allowed
    assert result.reason == "persistent_rate_limit"
    assert result.retry_after_seconds == 44


def test_database_limiter_failure_fails_closed_and_message_is_generic(monkeypatch):
    monkeypatch.setattr(protection, "is_database_configured", lambda: True)

    def fail(**kwargs):
        raise RuntimeError("postgres-password-and-host-must-not-leak")

    monkeypatch.setattr(protection, "consume_persistent_rate_limit", fail)
    result = reserve_action_slot({}, "report_submit", now=100)
    assert not result.allowed
    assert result.reason == "limiter_unavailable"
    message = public_limit_message(result)
    assert "temporarily unavailable" in message
    assert "postgres-password" not in message


def test_unknown_or_invalid_database_results_are_not_rendered_as_details():
    result = protection.RateLimitDecision(allowed=False, reason="limiter_unavailable")
    message = public_limit_message(result)
    assert "request-protection check" in message
    assert "database" not in message.lower()


def test_rate_limiter_policies_are_bounded_and_expected():
    assert ACTION_POLICIES["report_submit"].max_requests == 3
    assert ACTION_POLICIES["audio_transcription"].max_requests == 3
    assert ACTION_POLICIES["ai_assessment"].max_requests == 4
    assert all(policy.window_seconds == 600 for policy in ACTION_POLICIES.values())
    assert all(1 <= policy.max_requests <= 10 for policy in ACTION_POLICIES.values())


def test_database_limiter_logs_only_safe_error_metadata(monkeypatch, caplog):
    class FakeDatabaseError(RuntimeError):
        sqlstate = "42P01"

    monkeypatch.setattr(protection, "is_database_configured", lambda: True)

    def fail(**kwargs):
        raise FakeDatabaseError("do-not-log-this-secret-or-connection-string")

    monkeypatch.setattr(protection, "consume_persistent_rate_limit", fail)
    with caplog.at_level("WARNING", logger="smartcity.abuse_protection"):
        result = reserve_action_slot({}, "audio_transcription", now=1234)

    assert not result.allowed
    assert result.reason == "limiter_unavailable"
    assert "persistent_rate_limit_check_failed" in caplog.text
    assert "FakeDatabaseError" in caplog.text
    assert "42P01" in caplog.text
    assert "do-not-log-this-secret" not in caplog.text
