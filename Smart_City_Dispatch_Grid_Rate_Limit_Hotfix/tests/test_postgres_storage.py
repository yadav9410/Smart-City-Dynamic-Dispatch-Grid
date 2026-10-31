import re

import pytest

from smartcity.storage.postgres import (
    ALLOWED_STATUS_TRANSITIONS,
    VALID_STATUSES,
    _new_reference_code,
    create_public_report,
    prepare_report_payload,
)


def test_prepares_plain_text_report_and_does_not_add_location():
    payload = prepare_report_payload("  smoke\n near   gate ")
    assert payload["report_text"] == "smoke near gate"
    assert payload["input_method"] == "text"
    assert payload["location_source"] == "none"
    assert payload["location_consent"] is False
    assert payload["latitude"] is None
    assert payload["longitude"] is None


def test_rejects_empty_report():
    with pytest.raises(ValueError, match="cannot be empty"):
        prepare_report_payload(" \n  ")


def test_rejects_location_without_consent():
    with pytest.raises(ValueError, match="explicit user consent"):
        prepare_report_payload(
            "Smoke reported",
            latitude=28.61,
            longitude=77.39,
            location_source="gps",
        )


def test_accepts_gps_only_with_consent_and_coordinate_pair():
    payload = prepare_report_payload(
        "Smoke reported",
        latitude=28.61,
        longitude=77.39,
        location_source="gps",
        consent_to_store_location=True,
    )
    assert payload["location_consent"] is True
    assert payload["latitude"] == pytest.approx(28.61)
    assert payload["longitude"] == pytest.approx(77.39)


def test_rejects_half_coordinate_pair():
    with pytest.raises(ValueError, match="both be supplied"):
        prepare_report_payload(
            "Smoke reported",
            latitude=28.61,
            location_source="gps",
            consent_to_store_location=True,
        )


def test_rejects_invalid_coordinate():
    with pytest.raises(ValueError, match="latitude must be between"):
        prepare_report_payload(
            "Smoke reported",
            latitude=120,
            longitude=77.39,
            location_source="gps",
            consent_to_store_location=True,
        )


def test_accepts_manual_label_with_consent():
    payload = prepare_report_payload(
        "Person needs help",
        location_label="  Block A, Main   Gate ",
        location_source="manual",
        consent_to_store_location=True,
    )
    assert payload["location_label"] == "Block A, Main Gate"


def test_rejects_unknown_input_method():
    with pytest.raises(ValueError, match="input_method"):
        prepare_report_payload("Smoke reported", input_method="audio_file")


def test_status_graph_has_no_dispatched_status():
    assert "dispatched" not in VALID_STATUSES
    assert set(ALLOWED_STATUS_TRANSITIONS) == set(VALID_STATUSES)


def test_reference_code_format():
    assert re.fullmatch(r"RPT-\d{8}-[A-F0-9]{12}", _new_reference_code())


def test_create_report_requires_explicit_report_storage_consent():
    with pytest.raises(ValueError, match="Explicit consent"):
        create_public_report("Smoke reported")

    with pytest.raises(ValueError, match="Explicit consent"):
        create_public_report("Smoke reported", consent_to_store_report=False)


def test_persistent_rate_limit_rejects_unknown_action_before_connecting(monkeypatch):
    from smartcity.storage.postgres import consume_persistent_rate_limit

    def no_connect():
        raise AssertionError("Should validate before connecting")

    monkeypatch.setattr("smartcity.storage.postgres._connect", no_connect)
    with pytest.raises(ValueError, match="Unsupported rate-limit action"):
        consume_persistent_rate_limit(
            action="other_action",
            session_hash="a" * 64,
            max_requests=3,
            window_seconds=600,
        )


def test_persistent_rate_limit_validates_hash_and_bounds_before_connecting(monkeypatch):
    from smartcity.storage.postgres import consume_persistent_rate_limit

    def no_connect():
        raise AssertionError("Should validate before connecting")

    monkeypatch.setattr("smartcity.storage.postgres._connect", no_connect)
    with pytest.raises(ValueError, match="SHA-256 hex digest"):
        consume_persistent_rate_limit(
            action="report_submit",
            session_hash="bad", max_requests=3, window_seconds=600,
        )
    with pytest.raises(ValueError, match="max_requests"):
        consume_persistent_rate_limit(
            action="report_submit",
            session_hash="a" * 64, max_requests=0, window_seconds=600,
        )
    with pytest.raises(ValueError, match="window_seconds"):
        consume_persistent_rate_limit(
            action="report_submit",
            session_hash="a" * 64, max_requests=3, window_seconds=0,
        )
