"""Prototype-scale input and action-abuse safeguards.

The session limiter gives immediate feedback on repeated button presses. When
PostgreSQL is configured, a database-backed limiter additionally persists counts for
the same server-generated anonymous Streamlit session token across reruns. It is not
an IP-, account-, or user-level limit and must be supplemented by hosting-layer/WAF
controls before broad public use.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import logging
import secrets
import time
from typing import MutableMapping, Optional

from smartcity.storage.postgres import consume_persistent_rate_limit, is_database_configured

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ActionPolicy:
    max_requests: int
    window_seconds: int


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    reason: str = "allowed"
    retry_after_seconds: int = 0
    remaining: Optional[int] = None
    persistent: bool = False


ACTION_POLICIES = {
    "report_submit": ActionPolicy(max_requests=3, window_seconds=600),
    "audio_transcription": ActionPolicy(max_requests=3, window_seconds=600),
    "ai_assessment": ActionPolicy(max_requests=4, window_seconds=600),
}

_SESSION_NONCE_KEY = "_abuse_protection_session_nonce"
_SESSION_TIMESTAMPS_PREFIX = "_abuse_protection_timestamps_"


def _session_hash(state: MutableMapping[str, object]) -> str:
    """Hash a random server-generated session nonce before any database storage."""
    token = state.get(_SESSION_NONCE_KEY)
    if not isinstance(token, str) or len(token) < 32:
        token = secrets.token_urlsafe(32)
        state[_SESSION_NONCE_KEY] = token
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _consume_session_window(
    state: MutableMapping[str, object],
    action: str,
    policy: ActionPolicy,
    *,
    now: Optional[float] = None,
) -> RateLimitDecision:
    current = time.time() if now is None else float(now)
    key = f"{_SESSION_TIMESTAMPS_PREFIX}{action}"
    raw_timestamps = state.get(key, [])
    timestamps = [
        float(value)
        for value in raw_timestamps
        if isinstance(value, (int, float)) and current - float(value) < policy.window_seconds
    ] if isinstance(raw_timestamps, (list, tuple)) else []

    if len(timestamps) >= policy.max_requests:
        retry_after = max(1, int(policy.window_seconds - (current - timestamps[0]) + 0.999))
        state[key] = timestamps
        return RateLimitDecision(
            allowed=False,
            reason="session_rate_limit",
            retry_after_seconds=retry_after,
            remaining=0,
        )

    timestamps.append(current)
    # Bounded list: current policy windows are tiny, but never keep arbitrary state.
    state[key] = timestamps[-policy.max_requests:]
    return RateLimitDecision(
        allowed=True,
        remaining=max(0, policy.max_requests - len(timestamps)),
    )


def reserve_action_slot(
    state: MutableMapping[str, object],
    action: str,
    *,
    now: Optional[float] = None,
) -> RateLimitDecision:
    """Reserve one action slot, failing closed if configured DB limits cannot be checked.

    With no configured database, the in-session window is still applied so local demos
    remain testable. Public deployment should configure PostgreSQL and initialize the
    Phase 16.9 rate-limit table. All actions consume a slot when attempted, including
    failed external API attempts.
    """
    policy = ACTION_POLICIES.get(action)
    if policy is None:
        return RateLimitDecision(allowed=False, reason="unsupported_action")

    session_decision = _consume_session_window(state, action, policy, now=now)
    if not session_decision.allowed:
        return session_decision

    if not is_database_configured():
        return session_decision

    try:
        digest = _session_hash(state)
        result = consume_persistent_rate_limit(
            action=action,
            session_hash=digest,
            max_requests=policy.max_requests,
            window_seconds=policy.window_seconds,
        )
    except Exception as exc:
        # Keep the visitor-facing message generic, but write a safe diagnostic to
        # the server log. Never log the exception message, DSN, SQL parameters,
        # report text, location, or session token.
        sqlstate = getattr(exc, "sqlstate", None)
        logger.warning(
            "persistent_rate_limit_check_failed exception_type=%s sqlstate=%s",
            type(exc).__name__,
            sqlstate if isinstance(sqlstate, str) else "unavailable",
        )
        return RateLimitDecision(allowed=False, reason="limiter_unavailable", persistent=True)

    return RateLimitDecision(
        allowed=bool(result.get("allowed")),
        reason="allowed" if result.get("allowed") else "persistent_rate_limit",
        retry_after_seconds=max(0, int(result.get("retry_after_seconds", 0) or 0)),
        remaining=max(0, int(result.get("remaining", 0) or 0)),
        persistent=True,
    )


def public_limit_message(decision: RateLimitDecision) -> str:
    """Safe UI message; never includes implementation or database exception text."""
    if decision.reason == "limiter_unavailable":
        return (
            "The request-protection check is temporarily unavailable. Your action was not "
            "processed. Please try again later."
        )
    if decision.reason in {"session_rate_limit", "persistent_rate_limit"}:
        seconds = max(1, decision.retry_after_seconds)
        if seconds >= 60:
            wait_text = f"about {(seconds + 59) // 60} minute(s)"
        else:
            wait_text = f"about {seconds} second(s)"
        return f"Too many requests in a short period. Please wait {wait_text} before trying again."
    return "This action is temporarily unavailable. Please try again later."
