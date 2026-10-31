import pytest

from smartcity.safety import (
    EMERGENCY_INSTRUCTIONS,
    PUBLIC_PROTOTYPE_NOTICE,
    normalize_report_text,
)


def test_public_notice_says_no_real_dispatch():
    notice = PUBLIC_PROTOTYPE_NOTICE.lower()
    assert "does not contact emergency services" in notice
    assert "does not dispatch real responders" in notice


def test_emergency_instructions_point_to_112():
    assert "112" in EMERGENCY_INSTRUCTIONS
    assert "do not wait" in EMERGENCY_INSTRUCTIONS.lower()


def test_normalize_report_text_collapses_whitespace():
    assert normalize_report_text("  smoke\n near   gate ") == "smoke near gate"


def test_normalize_report_text_enforces_length_limit():
    assert normalize_report_text("abcdefgh", max_chars=5) == "abcde"


def test_normalize_report_text_rejects_non_string():
    with pytest.raises(TypeError):
        normalize_report_text(None)  # type: ignore[arg-type]


def test_normalize_report_text_rejects_invalid_limit():
    with pytest.raises(ValueError):
        normalize_report_text("hello", max_chars=0)
