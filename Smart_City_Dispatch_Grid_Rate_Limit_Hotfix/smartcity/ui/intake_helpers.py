"""Streamlit-independent validation helpers for public incident intake."""

from __future__ import annotations

from typing import Any

from smartcity.safety import normalize_report_text
from smartcity.storage.postgres import MAX_REPORT_CHARS


def effective_report_limit(configured_value: Any) -> int:
    """Clamp the configured text limit to a safe range."""
    try:
        configured = int(configured_value)
    except (TypeError, ValueError):
        configured = MAX_REPORT_CHARS
    return max(1, min(configured, MAX_REPORT_CHARS))


def validate_public_submission(
    report_text: str,
    *,
    consent_to_store_report: bool,
    confirm_prototype_only: bool,
    max_chars: int = MAX_REPORT_CHARS,
) -> str:
    """Validate acknowledgements and return normalized non-empty report text."""
    if confirm_prototype_only is not True:
        raise ValueError(
            "Please confirm that this is a prototype and not an emergency-service channel."
        )
    if consent_to_store_report is not True:
        raise ValueError("Report storage consent is required before submitting.")
    cleaned = normalize_report_text(report_text, max_chars=effective_report_limit(max_chars))
    if not cleaned:
        raise ValueError("Enter a brief description before submitting.")
    return cleaned


def safe_receipt_payload(receipt: dict[str, Any]) -> dict[str, Any]:
    """Reduce a storage response to fields suitable for a public receipt."""
    required = {"reference_code", "status", "submitted_at"}
    if not isinstance(receipt, dict) or not required.issubset(receipt):
        raise ValueError("Storage returned an incomplete report receipt.")
    return {
        "reference_code": receipt["reference_code"],
        "status": receipt["status"],
        "submitted_at": receipt["submitted_at"],
    }
