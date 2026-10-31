import math

import pytest

from smartcity.simulation.mock_resources import (
    build_mock_resources,
    build_simulation_scenario,
    straight_line_distance_km,
)


def test_creates_four_deterministic_synthetic_resources():
    first = build_mock_resources(28.6139, 77.2090)
    second = build_mock_resources(28.6139, 77.2090)
    assert first == second
    assert len(first) == 4
    assert len({item.resource_id for item in first}) == 4
    assert all(item.resource_id.startswith("SIM-") for item in first)


def test_mock_resource_coordinates_are_in_valid_ranges():
    for resource in build_mock_resources(28.6139, 77.2090):
        assert -90 <= resource.latitude <= 90
        assert -180 <= resource.longitude <= 180


@pytest.mark.parametrize(
    "lat,lon",
    [(91, 10), (-91, 10), (10, 181), (10, -181), (math.inf, 0), (0, math.nan), ("north", 10)],
)
def test_invalid_scenario_center_is_rejected(lat, lon):
    with pytest.raises(ValueError):
        build_mock_resources(lat, lon)


def test_distance_is_zero_for_same_point():
    assert straight_line_distance_km(28.6139, 77.2090, 28.6139, 77.2090) == pytest.approx(0.0)


def test_distance_between_distinct_points_is_positive_and_plausible():
    distance = straight_line_distance_km(28.6139, 77.2090, 28.7041, 77.1025)
    assert 10 < distance < 20


def test_distance_rejects_invalid_coordinates():
    with pytest.raises(ValueError):
        straight_line_distance_km(92, 0, 0, 0)


def test_scenario_explicitly_marks_simulation_and_no_dispatch():
    scenario = build_simulation_scenario(28.6139, 77.2090)
    assert scenario["scenario_is_simulated"] is True
    assert scenario["resource_positions_are_synthetic"] is True
    assert scenario["routes_are_road_navigation"] is False
    assert scenario["eta_calculated"] is False
    assert scenario["dispatch_triggered"] is False
    assert len(scenario["resources"]) == 4
    assert len(scenario["routes"]) == 4


def test_routes_are_straight_line_illustrations_only():
    scenario = build_simulation_scenario(0, 0)
    assert all(route["geometry_type"] == "straight_line_illustration" for route in scenario["routes"])
    assert all(route["distance_km"] >= 0 for route in scenario["routes"])
