"""Privacy-aware location validation helpers for the public prototype."""

from __future__ import annotations

import math
from typing import Any, Optional

from smartcity.storage.postgres import MAX_LOCATION_LABEL_CHARS


def parse_optional_coordinate_pair(latitude: Any, longitude: Any) -> tuple[Optional[float], Optional[float]]:
    """Parse a coordinate pair, allowing both values to be blank."""
    lat_text = "" if latitude is None else str(latitude).strip()
    lon_text = "" if longitude is None else str(longitude).strip()
    if not lat_text and not lon_text:
        return None, None
    if not lat_text or not lon_text:
        raise ValueError("Enter both latitude and longitude, or leave both blank.")

    try:
        lat = float(lat_text)
        lon = float(lon_text)
    except (TypeError, ValueError) as exc:
        raise ValueError("Latitude and longitude must be valid numbers.") from exc

    if not math.isfinite(lat) or not -90 <= lat <= 90:
        raise ValueError("Latitude must be between -90 and 90.")
    if not math.isfinite(lon) or not -180 <= lon <= 180:
        raise ValueError("Longitude must be between -180 and 180.")
    return lat, lon


def prepare_consented_location(
    *,
    latitude: Any = None,
    longitude: Any = None,
    location_label: Any = None,
    location_source: str = "none",
    consent_to_store_location: bool = False,
) -> dict[str, Any]:
    """Build database location fields; omit all location data without consent."""
    if consent_to_store_location is not True:
        return {
            "latitude": None,
            "longitude": None,
            "location_label": None,
            "location_source": "none",
            "consent_to_store_location": False,
        }

    lat, lon = parse_optional_coordinate_pair(latitude, longitude)
    if location_source not in {"none", "gps", "manual"}:
        raise ValueError("Choose GPS or manual location for the shared position.")

    label: Optional[str] = None
    if location_label is not None:
        if not isinstance(location_label, str):
            raise ValueError("Location label must be text.")
        label = " ".join(location_label.split()) or None
        if label is not None and len(label) > MAX_LOCATION_LABEL_CHARS:
            raise ValueError(
                f"Location label must be at most {MAX_LOCATION_LABEL_CHARS} characters."
            )

    has_coordinates = lat is not None and lon is not None
    has_label = label is not None
    if not has_coordinates and not has_label:
        return {
            "latitude": None,
            "longitude": None,
            "location_label": None,
            "location_source": "none",
            "consent_to_store_location": False,
        }

    source = location_source
    if source == "none":
        source = "manual"
    if source == "gps" and not has_coordinates:
        raise ValueError("GPS location requires both coordinates.")
    if source == "manual" and not (has_coordinates or has_label):
        raise ValueError("Manual location requires coordinates or a location label.")

    return {
        "latitude": lat,
        "longitude": lon,
        "location_label": label,
        "location_source": source,
        "consent_to_store_location": True,
    }


def prepare_required_consented_location(
    *,
    latitude: Any = None,
    longitude: Any = None,
    location_label: Any = None,
    location_source: str = "none",
    consent_to_store_location: bool = False,
) -> dict[str, Any]:
    """Require a usable location and explicit consent before report submission.

    A visitor may provide either a valid coordinate pair (GPS, map pin, or
    manual entry) or an address/landmark label. Location is not stored unless
    the separate location-consent checkbox is checked.
    """
    lat, lon = parse_optional_coordinate_pair(latitude, longitude)

    if location_label is not None and not isinstance(location_label, str):
        raise ValueError("Location label must be text.")
    cleaned_label = " ".join((location_label or "").split())
    has_coordinates = lat is not None and lon is not None
    has_label = bool(cleaned_label)

    if not has_coordinates and not has_label:
        raise ValueError(
            "Location is required. Use your current location, choose a map pin, "
            "enter coordinates, or add an address/landmark."
        )
    if consent_to_store_location is not True:
        raise ValueError(
            "Please consent to storing the selected location with your report before submitting."
        )

    return prepare_consented_location(
        latitude=lat,
        longitude=lon,
        location_label=cleaned_label,
        location_source=location_source,
        consent_to_store_location=True,
    )
