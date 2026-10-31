from datetime import datetime, timezone

import pytest

from smartcity.storage.postgres import MAX_REPORT_CHARS
from smartcity.ui.intake_helpers import (
    effective_report_limit,
    safe_receipt_payload,
    validate_public_submission,
)


def test_effective_report_limit_is_bounded():
    assert effective_report_limit(99999) == MAX_REPORT_CHARS
    assert effective_report_limit(250) == 250
    assert effective_report_limit("not a number") == MAX_REPORT_CHARS
    assert effective_report_limit(0) == 1


def test_validate_public_submission_requires_prototype_acknowledgement():
    with pytest.raises(ValueError, match="confirm that this is a prototype"):
        validate_public_submission(
            "A fictional test report",
            consent_to_store_report=True,
            confirm_prototype_only=False,
        )


def test_validate_public_submission_requires_storage_consent():
    with pytest.raises(ValueError, match="storage consent is required"):
        validate_public_submission(
            "A fictional test report",
            consent_to_store_report=False,
            confirm_prototype_only=True,
        )


def test_validate_public_submission_normalizes_text_and_rejects_empty():
    assert validate_public_submission(
        "  Smoke\n near   gate ",
        consent_to_store_report=True,
        confirm_prototype_only=True,
    ) == "Smoke near gate"
    with pytest.raises(ValueError, match="brief description"):
        validate_public_submission(
            " \n  ",
            consent_to_store_report=True,
            confirm_prototype_only=True,
        )


def test_validate_public_submission_enforces_character_limit():
    assert validate_public_submission(
        "abcdefgh",
        consent_to_store_report=True,
        confirm_prototype_only=True,
        max_chars=5,
    ) == "abcde"


def test_safe_receipt_payload_returns_only_public_receipt_fields():
    receipt = {
        "reference_code": "RPT-20261024-ABCDEF123456",
        "status": "recorded",
        "submitted_at": datetime(2026, 10, 24, tzinfo=timezone.utc),
        "report_text": "private report text",
        "latitude": 28.6,
        "longitude": 77.3,
    }
    assert safe_receipt_payload(receipt) == {
        "reference_code": "RPT-20261024-ABCDEF123456",
        "status": "recorded",
        "submitted_at": receipt["submitted_at"],
    }


def test_safe_receipt_payload_rejects_incomplete_receipt():
    with pytest.raises(ValueError, match="incomplete report receipt"):
        safe_receipt_payload({"reference_code": "RPT-1"})
