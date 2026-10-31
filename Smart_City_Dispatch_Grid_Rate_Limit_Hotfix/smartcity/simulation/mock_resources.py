"""Deterministic, synthetic responder markers and illustrative route geometry.

Nothing in this module represents real people, vehicles, availability, live GPS, road
routing, ETA, or dispatch. Resource positions are generated around a chosen map center.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable


@dataclass(frozen=True)
class MockResource:
    resource_id: str
    resource_type: str
    label: str
    latitude: float
    longitude: float
    icon: str
    color: str


# These positions are relative offsets in kilometres from the scenario center.
# They intentionally do not correspond to any real station or vehicle.
_RESOURCE_SPECS = (
    ("SIM-MED-01", "Medical unit", "Synthetic medical unit", "plus", "blue", 0.9, 0.5),
    ("SIM-FIRE-01", "Fire & rescue", "Synthetic fire/rescue unit", "fire-extinguisher", "red", -1.2, 0.7),
    ("SIM-RES-01", "Rescue unit", "Synthetic rescue unit", "life-ring", "green", 0.4, -1.6),
    ("SIM-SUP-01", "Safety support", "Synthetic support unit", "shield", "purple", -1.5, -1.1),
)


def _validate_coordinates(latitude: float, longitude: float) -> tuple[float, float]:
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError) as exc:
        raise ValueError("Scenario center must contain numeric latitude and longitude.") from exc
    if not math.isfinite(lat) or not -90 <= lat <= 90:
        raise ValueError("Scenario latitude must be between -90 and 90.")
    if not math.isfinite(lon) or not -180 <= lon <= 180:
        raise ValueError("Scenario longitude must be between -180 and 180.")
    return lat, lon


def _offset_coordinate(latitude: float, longitude: float, north_km: float, east_km: float) -> tuple[float, float]:
    """Convert a small synthetic kilometre offset to a valid lat/lon pair."""
    # 1 degree latitude is approximately 111.32 km. Prevent longitude instability near poles.
    shifted_lat = latitude + north_km / 111.32
    shifted_lat = max(-89.5, min(89.5, shifted_lat))
    cos_lat = max(abs(math.cos(math.radians(shifted_lat))), 0.05)
    shifted_lon = longitude + east_km / (111.32 * cos_lat)
    # Normalize longitude across the international date line.
    shifted_lon = ((shifted_lon + 180.0) % 360.0) - 180.0
    return round(shifted_lat, 7), round(shifted_lon, 7)


def build_mock_resources(latitude: float, longitude: float) -> list[MockResource]:
    """Create deterministic fictional units around a validated scenario center."""
    lat, lon = _validate_coordinates(latitude, longitude)
    resources: list[MockResource] = []
    for resource_id, resource_type, label, icon, color, north_km, east_km in _RESOURCE_SPECS:
        unit_lat, unit_lon = _offset_coordinate(lat, lon, north_km, east_km)
        resources.append(
            MockResource(
                resource_id=resource_id,
                resource_type=resource_type,
                label=label,
                latitude=unit_lat,
                longitude=unit_lon,
                icon=icon,
                color=color,
            )
        )
    return resources


def straight_line_distance_km(
    start_latitude: float,
    start_longitude: float,
    end_latitude: float,
    end_longitude: float,
) -> float:
    """Return great-circle distance for demonstration only; not road distance or ETA."""
    lat1, lon1 = _validate_coordinates(start_latitude, start_longitude)
    lat2, lon2 = _validate_coordinates(end_latitude, end_longitude)
    radius_km = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    # Clamp due to floating point noise.
    a = min(1.0, max(0.0, a))
    return radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def build_simulation_scenario(latitude: float, longitude: float) -> dict:
    """Build a display-ready scenario using synthetic units and illustrative distances."""
    lat, lon = _validate_coordinates(latitude, longitude)
    resources = build_mock_resources(lat, lon)
    routes = [
        {
            "resource_id": resource.resource_id,
            "start": (resource.latitude, resource.longitude),
            "end": (lat, lon),
            "distance_km": round(
                straight_line_distance_km(resource.latitude, resource.longitude, lat, lon), 2
            ),
            "geometry_type": "straight_line_illustration",
        }
        for resource in resources
    ]
    return {
        "scenario_center": (lat, lon),
        "scenario_is_simulated": True,
        "resource_positions_are_synthetic": True,
        "routes_are_road_navigation": False,
        "eta_calculated": False,
        "dispatch_triggered": False,
        "resources": resources,
        "routes": routes,
    }
