import math

import pytest

from smartcity.ui.location_helpers import (
    parse_optional_coordinate_pair,
    prepare_consented_location,
)


def test_blank_coordinate_pair_is_allowed():
    assert parse_optional_coordinate_pair("", "  ") == (None, None)


def test_valid_coordinate_pair_is_parsed():
    assert parse_optional_coordinate_pair("28.6139", "77.2090") == (28.6139, 77.209)


@pytest.mark.parametrize(
    "lat,lon",
    [("28.6", ""), ("", "77.2"), ("north", "77.2"), ("91", "77.2"), ("28.6", "181")],
)
def test_invalid_coordinate_pairs_are_rejected(lat, lon):
    with pytest.raises(ValueError):
        parse_optional_coordinate_pair(lat, lon)


def test_non_finite_coordinates_are_rejected():
    with pytest.raises(ValueError, match="Latitude"):
        parse_optional_coordinate_pair(str(math.inf), "77.2")


def test_no_location_consent_omits_all_location_data():
    result = prepare_consented_location(
        latitude=28.6139,
        longitude=77.209,
        location_label="A private address",
        location_source="gps",
        consent_to_store_location=False,
    )
    assert result == {
        "latitude": None,
        "longitude": None,
        "location_label": None,
        "location_source": "none",
        "consent_to_store_location": False,
    }


def test_consented_gps_location_is_prepared():
    result = prepare_consented_location(
        latitude=28.6139,
        longitude=77.209,
        location_source="gps",
        consent_to_store_location=True,
    )
    assert result["latitude"] == 28.6139
    assert result["longitude"] == 77.209
    assert result["location_source"] == "gps"
    assert result["consent_to_store_location"] is True


def test_manual_label_without_coordinates_is_allowed():
    result = prepare_consented_location(
        location_label="  Near   main gate  ",
        location_source="manual",
        consent_to_store_location=True,
    )
    assert result["location_label"] == "Near main gate"
    assert result["latitude"] is None
    assert result["longitude"] is None
    assert result["location_source"] == "manual"


def test_location_source_is_inferred_for_manual_location():
    result = prepare_consented_location(
        location_label="Landmark",
        consent_to_store_location=True,
    )
    assert result["location_source"] == "manual"


def test_gps_requires_coordinates():
    with pytest.raises(ValueError, match="GPS location requires"):
        prepare_consented_location(
            location_label="A place",
            location_source="gps",
            consent_to_store_location=True,
        )


def test_location_label_length_is_limited():
    with pytest.raises(ValueError, match="at most 250 characters"):
        prepare_consented_location(
            location_label="x" * 251,
            location_source="manual",
            consent_to_store_location=True,
        )


def test_required_location_rejects_missing_location():
    from smartcity.ui.location_helpers import prepare_required_consented_location

    with pytest.raises(ValueError, match="Location is required"):
        prepare_required_consented_location(consent_to_store_location=True)


def test_required_location_requires_separate_location_consent():
    from smartcity.ui.location_helpers import prepare_required_consented_location

    with pytest.raises(ValueError, match="consent to storing the selected location"):
        prepare_required_consented_location(
            latitude=28.6139,
            longitude=77.2090,
            location_source="gps",
            consent_to_store_location=False,
        )


def test_required_location_accepts_consented_map_or_gps_coordinates():
    from smartcity.ui.location_helpers import prepare_required_consented_location

    result = prepare_required_consented_location(
        latitude=28.6139,
        longitude=77.2090,
        location_source="gps",
        consent_to_store_location=True,
    )
    assert result["latitude"] == 28.6139
    assert result["longitude"] == 77.2090
    assert result["location_source"] == "gps"
    assert result["consent_to_store_location"] is True


def test_required_location_accepts_address_label_with_consent():
    from smartcity.ui.location_helpers import prepare_required_consented_location

    result = prepare_required_consented_location(
        location_label="  Near   Gate 2  ",
        location_source="none",
        consent_to_store_location=True,
    )
    assert result["location_label"] == "Near Gate 2"
    assert result["location_source"] == "manual"
    assert result["consent_to_store_location"] is True
