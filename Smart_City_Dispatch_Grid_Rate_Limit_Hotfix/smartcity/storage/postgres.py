"""PostgreSQL persistence for the public Smart City Dispatch Grid prototype.

This module stores user-submitted text reports and consented location data.
It does not contact emergency services or dispatch real responders.

Security notes:
- Keep DATABASE_URL in environment/Streamlit secrets; never commit it.
- Do not store raw audio. Voice submissions should store only a user-reviewed transcript.
- Treat get_public_report() and list_public_reports() as operator-only helpers.
  Do not expose them in a public UI until authentication/authorization is implemented.
- Audit metadata is deliberately limited to non-report content.
"""

from __future__ import annotations

from datetime import datetime, timezone
import math
import os
import re
import secrets
from typing import Any, Optional
from uuid import UUID, uuid4

from smartcity.config import get_secret, settings
from smartcity.safety import normalize_report_text

MAX_REPORT_CHARS = 3000
MAX_LOCATION_LABEL_CHARS = 250
CONNECT_TIMEOUT_SECONDS = 30

VALID_INPUT_METHODS = frozenset({"text", "voice_transcription"})
VALID_LOCATION_SOURCES = frozenset({"none", "gps", "manual"})
VALID_STATUSES = frozenset(
    {
        "recorded",
        "processing",
        "needs_review",
        "awaiting_operator_review",
        "reviewed",
        "closed",
        "failed",
    }
)

# Explicit transitions make accidental/skipped workflow states less likely.
ALLOWED_STATUS_TRANSITIONS = {
    "recorded": frozenset({"processing", "needs_review", "closed"}),
    "processing": frozenset(
        {"needs_review", "awaiting_operator_review", "failed", "closed"}
    ),
    "needs_review": frozenset(
        {"processing", "awaiting_operator_review", "reviewed", "closed"}
    ),
    "awaiting_operator_review": frozenset({"reviewed", "needs_review", "closed"}),
    "reviewed": frozenset({"needs_review", "closed"}),
    "failed": frozenset({"processing", "closed"}),
    "closed": frozenset(),
}


class DatabaseConfigurationError(RuntimeError):
    """Raised when PostgreSQL is not configured or the driver is missing."""


def _database_url() -> str:
    """Resolve a PostgreSQL URL without printing or exposing the secret."""
    url = os.getenv("DATABASE_URL") or get_secret("DATABASE_URL") or settings.database_url
    if not url:
        raise DatabaseConfigurationError(
            "DATABASE_URL is not configured. Add it to Colab Secrets, local "
            ".streamlit/secrets.toml, or the deployment platform's secrets settings."
        )
    if not str(url).startswith(("postgresql://", "postgres://")):
        raise DatabaseConfigurationError(
            "DATABASE_URL must be a PostgreSQL connection URL."
        )
    return str(url)


def _connect():
    """Open a short-lived PostgreSQL connection with dictionary row results."""
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:  # Keep basic validation tests usable without a driver.
        raise DatabaseConfigurationError(
            "PostgreSQL driver missing. Install requirements.txt (psycopg[binary])."
        ) from exc

    # Do not pass libpq's ``options`` startup parameter here. Neon pooled URLs
    # route through PgBouncer, which rejects untracked startup options such as
    # statement_timeout and idle_in_transaction_session_timeout. That rejection
    # surfaces from psycopg as OperationalError (often without a SQLSTATE), causing
    # the fail-closed rate limiter to block every protected action.
    # Keep the connection handshake timeout at 30s to accommodate a waking Neon
    # compute. All SQL in this module is short, parameterized application work.
    return psycopg.connect(
        _database_url(),
        connect_timeout=CONNECT_TIMEOUT_SECONDS,
        row_factory=dict_row,
    )


_CREATE_REPORTS_TABLE = """
CREATE TABLE IF NOT EXISTS public_incident_reports (
    id UUID PRIMARY KEY,
    reference_code VARCHAR(32) NOT NULL UNIQUE,
    report_text TEXT NOT NULL
        CHECK (char_length(report_text) BETWEEN 1 AND 3000),
    input_method VARCHAR(32) NOT NULL
        CHECK (input_method IN ('text', 'voice_transcription')),
    location_label VARCHAR(250),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    location_source VARCHAR(16) NOT NULL DEFAULT 'none'
        CHECK (location_source IN ('none', 'gps', 'manual')),
    location_consent BOOLEAN NOT NULL DEFAULT FALSE,
    status VARCHAR(32) NOT NULL DEFAULT 'recorded'
        CHECK (status IN (
            'recorded', 'processing', 'needs_review',
            'awaiting_operator_review', 'reviewed', 'closed', 'failed'
        )),
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((latitude IS NULL) = (longitude IS NULL)),
    CHECK (latitude IS NULL OR latitude BETWEEN -90 AND 90),
    CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180),
    CHECK (
        location_consent OR (
            latitude IS NULL AND longitude IS NULL AND
            location_label IS NULL AND location_source = 'none'
        )
    )
)
"""

_CREATE_REPORTS_INDEX = """
CREATE INDEX IF NOT EXISTS idx_public_incident_reports_status_time
ON public_incident_reports (status, submitted_at DESC)
"""

_CREATE_AUDIT_TABLE = """
CREATE TABLE IF NOT EXISTS public_audit_events (
    id UUID PRIMARY KEY,
    report_id UUID REFERENCES public_incident_reports(id) ON DELETE SET NULL,
    event_type VARCHAR(80) NOT NULL,
    actor_role VARCHAR(32) NOT NULL
        CHECK (actor_role IN ('public_user', 'system', 'operator')),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

_CREATE_AUDIT_INDEX = """
CREATE INDEX IF NOT EXISTS idx_public_audit_events_report_time
ON public_audit_events (report_id, created_at DESC)
"""

# This table stores only a hash of an anonymous, server-generated Streamlit-session
# token, an allow-listed action name, and bounded counters/timestamps. It is not an
# IP-address or account-level rate limiter.
_CREATE_RATE_LIMIT_TABLE = """
CREATE TABLE IF NOT EXISTS public.public_request_limits (
    session_hash CHAR(64) NOT NULL
        CHECK (session_hash ~ '^[0-9a-f]{64}$'),
    action VARCHAR(32) NOT NULL
        CHECK (action IN ('report_submit', 'audio_transcription', 'ai_assessment')),
    window_started_at TIMESTAMPTZ NOT NULL,
    request_count INTEGER NOT NULL CHECK (request_count BETWEEN 1 AND 1001),
    last_request_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (session_hash, action)
)
"""

_CREATE_RATE_LIMIT_CLEANUP_INDEX = """
CREATE INDEX IF NOT EXISTS idx_public_request_limits_last_request
ON public.public_request_limits (last_request_at)
"""

_RATE_LIMIT_ACTIONS = frozenset({"report_submit", "audio_transcription", "ai_assessment"})


def initialize_database() -> None:
    """Create the Phase 16.2 tables and indexes if they do not exist.

    Safe to run more than once. This must be run against the intended hosted
    PostgreSQL database; it does not migrate or delete the earlier Colab SQLite DB.
    """
    statements = (
        _CREATE_REPORTS_TABLE,
        _CREATE_REPORTS_INDEX,
        _CREATE_AUDIT_TABLE,
        _CREATE_AUDIT_INDEX,
        _CREATE_RATE_LIMIT_TABLE,
        _CREATE_RATE_LIMIT_CLEANUP_INDEX,
    )
    with _connect() as conn:
        with conn.cursor() as cur:
            for statement in statements:
                cur.execute(statement)


def is_database_configured() -> bool:
    """Return whether a PostgreSQL URL is present (does not connect)."""
    try:
        _database_url()
        return True
    except DatabaseConfigurationError:
        return False



def consume_persistent_rate_limit(
    *,
    action: str,
    session_hash: str,
    max_requests: int,
    window_seconds: int,
) -> dict[str, Any]:
    """Atomically consume one database-backed action slot for an anonymous session.

    The caller must pass a SHA-256 hex digest of a random server-side session token,
    not an IP address, report text, or direct identifier. This provides persistence
    across reruns for the same Streamlit session token; it does not prevent an attacker
    from creating fresh sessions and is not a replacement for edge/WAF rate limits.

    Run initialize_database() after upgrading so the rate-limit table exists.
    """
    if action not in _RATE_LIMIT_ACTIONS:
        raise ValueError("Unsupported rate-limit action.")
    if not isinstance(session_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", session_hash):
        raise ValueError("session_hash must be a SHA-256 hex digest.")
    if isinstance(max_requests, bool) or not isinstance(max_requests, int) or not 1 <= max_requests <= 1000:
        raise ValueError("max_requests must be an integer between 1 and 1000.")
    if isinstance(window_seconds, bool) or not isinstance(window_seconds, int) or not 1 <= window_seconds <= 86400:
        raise ValueError("window_seconds must be an integer between 1 and 86400.")

    with _connect() as conn:
        with conn.cursor() as cur:
            # Opportunistic cleanup avoids an unbounded buildup of stale anonymous
            # session keys without running a full-table cleanup on every request.
            if secrets.randbelow(50) == 0:
                cur.execute(
                    "DELETE FROM public.public_request_limits "
                    "WHERE last_request_at < now() - interval '24 hours'"
                )
            cur.execute(
                """
                INSERT INTO public.public_request_limits
                    (session_hash, action, window_started_at, request_count, last_request_at)
                VALUES (%s, %s, now(), 1, now())
                ON CONFLICT (session_hash, action) DO UPDATE SET
                    window_started_at = CASE
                        WHEN public.public_request_limits.window_started_at
                             + (%s * interval '1 second') <= now()
                        THEN now()
                        ELSE public.public_request_limits.window_started_at
                    END,
                    request_count = CASE
                        WHEN public.public_request_limits.window_started_at
                             + (%s * interval '1 second') <= now()
                        THEN 1
                        ELSE LEAST(public.public_request_limits.request_count + 1, %s + 1)
                    END,
                    last_request_at = now()
                RETURNING request_count, window_started_at,
                    window_started_at + (%s * interval '1 second') AS reset_at
                """,
                (session_hash, action, window_seconds, window_seconds, max_requests, window_seconds),
            )
            row = cur.fetchone()

    if not row:
        raise RuntimeError("Could not verify action rate limit.")
    reset_at = row["reset_at"]
    now_utc = datetime.now(timezone.utc)
    try:
        retry_after = max(0, math.ceil((reset_at - now_utc).total_seconds()))
    except (TypeError, AttributeError):
        retry_after = window_seconds
    count = int(row["request_count"])
    return {
        "allowed": count <= max_requests,
        "remaining": max(0, max_requests - count),
        "retry_after_seconds": retry_after,
        "request_count": count,
    }

def _finite_coordinate(name: str, value: Optional[float], minimum: float, maximum: float):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a numeric coordinate.")
    try:
        coordinate = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a numeric coordinate.") from exc
    if not math.isfinite(coordinate) or not minimum <= coordinate <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return coordinate


def prepare_report_payload(
    report_text: str,
    *,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    location_label: Optional[str] = None,
    location_source: str = "none",
    consent_to_store_location: bool = False,
    input_method: str = "text",
) -> dict[str, Any]:
    """Validate and normalize a report before it reaches the database.

    Call this from the app only after the user has explicitly agreed to store
    the report. Location is separately stored only with explicit location consent.
    """
    max_chars = max(1, min(int(settings.max_report_chars), MAX_REPORT_CHARS))
    cleaned_text = normalize_report_text(report_text, max_chars=max_chars)
    if not cleaned_text:
        raise ValueError("Incident report cannot be empty.")

    if input_method not in VALID_INPUT_METHODS:
        raise ValueError("input_method must be 'text' or 'voice_transcription'.")

    if location_source not in VALID_LOCATION_SOURCES:
        raise ValueError("location_source must be 'none', 'gps', or 'manual'.")

    lat = _finite_coordinate("latitude", latitude, -90, 90)
    lon = _finite_coordinate("longitude", longitude, -180, 180)
    if (lat is None) != (lon is None):
        raise ValueError("Latitude and longitude must either both be supplied or both be omitted.")

    label = None
    if location_label is not None:
        if not isinstance(location_label, str):
            raise ValueError("location_label must be text.")
        label = " ".join(location_label.split())
        if not label:
            label = None
        elif len(label) > MAX_LOCATION_LABEL_CHARS:
            raise ValueError(
                f"location_label must be at most {MAX_LOCATION_LABEL_CHARS} characters."
            )

    has_location = lat is not None or label is not None
    if has_location and not consent_to_store_location:
        raise ValueError("Location can only be stored after explicit user consent.")
    if not has_location and location_source != "none":
        raise ValueError("A location source was provided without location data.")
    if has_location and location_source == "none":
        raise ValueError("Choose 'gps' or 'manual' for a shared location.")
    if location_source == "gps" and (lat is None or lon is None):
        raise ValueError("GPS location requires both latitude and longitude.")
    if location_source == "manual" and not has_location:
        raise ValueError("Manual location requires an address/label or coordinates.")

    return {
        "report_text": cleaned_text,
        "input_method": input_method,
        "latitude": lat,
        "longitude": lon,
        "location_label": label,
        "location_source": location_source,
        "location_consent": bool(consent_to_store_location and has_location),
    }


def _new_reference_code() -> str:
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    suffix = secrets.token_hex(6).upper()
    return f"RPT-{day}-{suffix}"


def _insert_audit_event(
    cur,
    *,
    report_id: UUID,
    event_type: str,
    actor_role: str,
    metadata: dict[str, Any],
) -> None:
    """Internal audit writer; only pass controlled, non-sensitive metadata."""
    if actor_role not in {"public_user", "system", "operator"}:
        raise ValueError("Invalid audit actor role.")
    if event_type not in {"report_recorded", "status_changed"}:
        raise ValueError("Invalid audit event type.")

    try:
        from psycopg.types.json import Jsonb
    except ImportError as exc:
        raise DatabaseConfigurationError(
            "PostgreSQL driver missing. Install requirements.txt (psycopg[binary])."
        ) from exc

    cur.execute(
        """
        INSERT INTO public_audit_events
            (id, report_id, event_type, actor_role, metadata)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (uuid4(), report_id, event_type, actor_role, Jsonb(metadata)),
    )


def create_public_report(
    report_text: str,
    *,
    consent_to_store_report: bool = False,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    location_label: Optional[str] = None,
    location_source: str = "none",
    consent_to_store_location: bool = False,
    input_method: str = "text",
) -> dict[str, Any]:
    """Persist a submitted report and return a safe receipt (not dispatch status).

    Explicit report-storage agreement is required. Location consent is separate.
    Raw audio is never accepted here.
    """
    if consent_to_store_report is not True:
        raise ValueError("Explicit consent to store the incident report is required.")

    payload = prepare_report_payload(
        report_text,
        latitude=latitude,
        longitude=longitude,
        location_label=location_label,
        location_source=location_source,
        consent_to_store_location=consent_to_store_location,
        input_method=input_method,
    )
    report_id = uuid4()
    reference_code = _new_reference_code()

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public_incident_reports (
                    id, reference_code, report_text, input_method,
                    location_label, latitude, longitude,
                    location_source, location_consent, status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'recorded')
                RETURNING reference_code, status, submitted_at
                """,
                (
                    report_id,
                    reference_code,
                    payload["report_text"],
                    payload["input_method"],
                    payload["location_label"],
                    payload["latitude"],
                    payload["longitude"],
                    payload["location_source"],
                    payload["location_consent"],
                ),
            )
            receipt = dict(cur.fetchone())
            _insert_audit_event(
                cur,
                report_id=report_id,
                event_type="report_recorded",
                actor_role="public_user",
                metadata={
                    "input_method": payload["input_method"],
                    "location_shared": payload["location_consent"],
                    "status": "recorded",
                },
            )

    # Return only receipt fields; never tell the public that help is on the way.
    return receipt


def get_public_report_receipt(reference_code: str) -> Optional[dict[str, Any]]:
    """Return minimal receipt data for display to a user holding the reference code."""
    if not isinstance(reference_code, str) or not reference_code.strip():
        return None
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT reference_code, status, submitted_at
                FROM public_incident_reports
                WHERE reference_code = %s
                """,
                (reference_code.strip().upper(),),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def get_public_report(reference_code: str) -> Optional[dict[str, Any]]:
    """Return a full report record. OPERATOR-ONLY; never expose publicly."""
    if not isinstance(reference_code, str) or not reference_code.strip():
        return None
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, reference_code, report_text, input_method,
                       location_label, latitude, longitude, location_source,
                       location_consent, status, submitted_at, updated_at
                FROM public_incident_reports
                WHERE reference_code = %s
                """,
                (reference_code.strip().upper(),),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def list_public_reports(
    *, limit: int = 100, status: Optional[str] = None
) -> list[dict[str, Any]]:
    """List reports for an authenticated operator view only.

    Do not call this from public-facing routes. Operator authentication and
    authorization are implemented in a later phase.
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
        raise ValueError("limit must be an integer between 1 and 500.")
    if status is not None and status not in VALID_STATUSES:
        raise ValueError(f"status must be one of: {', '.join(sorted(VALID_STATUSES))}.")

    with _connect() as conn:
        with conn.cursor() as cur:
            if status is None:
                cur.execute(
                    """
                    SELECT id, reference_code, report_text, input_method,
                           location_label, latitude, longitude, location_source,
                           location_consent, status, submitted_at, updated_at
                    FROM public_incident_reports
                    ORDER BY submitted_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
            else:
                cur.execute(
                    """
                    SELECT id, reference_code, report_text, input_method,
                           location_label, latitude, longitude, location_source,
                           location_consent, status, submitted_at, updated_at
                    FROM public_incident_reports
                    WHERE status = %s
                    ORDER BY submitted_at DESC
                    LIMIT %s
                    """,
                    (status, limit),
                )
            return [dict(row) for row in cur.fetchall()]


def update_public_report_status(
    reference_code: str,
    new_status: str,
    *,
    actor_role: str = "system",
) -> dict[str, Any]:
    """Update an internal workflow status and append a minimal audit event.

    These workflow statuses are not real dispatch states. No 'dispatched' status
    exists in this storage contract; any resource assignment remains simulated.
    """
    if not isinstance(reference_code, str) or not reference_code.strip():
        raise ValueError("reference_code is required.")
    if new_status not in VALID_STATUSES:
        raise ValueError(f"new_status must be one of: {', '.join(sorted(VALID_STATUSES))}.")
    if actor_role not in {"system", "operator"}:
        raise ValueError("Status changes must be attributed to system or operator.")

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, status FROM public_incident_reports WHERE reference_code = %s FOR UPDATE",
                (reference_code.strip().upper(),),
            )
            current = cur.fetchone()
            if current is None:
                raise LookupError("No report found for that reference code.")

            current_status = current["status"]
            if new_status == current_status:
                cur.execute(
                    """
                    SELECT reference_code, status, submitted_at, updated_at
                    FROM public_incident_reports WHERE id = %s
                    """,
                    (current["id"],),
                )
                return dict(cur.fetchone())

            allowed = ALLOWED_STATUS_TRANSITIONS.get(current_status, frozenset())
            if new_status not in allowed:
                raise ValueError(
                    f"Status transition {current_status!r} -> {new_status!r} is not allowed."
                )

            cur.execute(
                """
                UPDATE public_incident_reports
                SET status = %s, updated_at = now()
                WHERE id = %s
                RETURNING reference_code, status, submitted_at, updated_at
                """,
                (new_status, current["id"]),
            )
            updated = dict(cur.fetchone())
            _insert_audit_event(
                cur,
                report_id=current["id"],
                event_type="status_changed",
                actor_role=actor_role,
                metadata={"status_from": current_status, "status_to": new_status},
            )
            return updated


def list_audit_events(*, reference_code: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
    """Return non-content audit metadata. Keep this behind operator authorization."""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
        raise ValueError("limit must be an integer between 1 and 500.")

    with _connect() as conn:
        with conn.cursor() as cur:
            if reference_code:
                cur.execute(
                    """
                    SELECT a.id, r.reference_code, a.event_type, a.actor_role,
                           a.metadata, a.created_at
                    FROM public_audit_events AS a
                    LEFT JOIN public_incident_reports AS r ON r.id = a.report_id
                    WHERE r.reference_code = %s
                    ORDER BY a.created_at DESC
                    LIMIT %s
                    """,
                    (reference_code.strip().upper(), limit),
                )
            else:
                cur.execute(
                    """
                    SELECT a.id, r.reference_code, a.event_type, a.actor_role,
                           a.metadata, a.created_at
                    FROM public_audit_events AS a
                    LEFT JOIN public_incident_reports AS r ON r.id = a.report_id
                    ORDER BY a.created_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
            return [dict(row) for row in cur.fetchall()]
