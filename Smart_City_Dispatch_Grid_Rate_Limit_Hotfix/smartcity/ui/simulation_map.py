"""Opt-in map overlay for purely fictional resource and route visualization."""

from __future__ import annotations

import folium
import streamlit as st
from streamlit_folium import st_folium

from smartcity.simulation.mock_resources import build_simulation_scenario

# Generic map center in India. It is not the visitor's location or an actual incident.
_DEMO_CENTER = (22.9734, 78.6569)


def _add_simulation_layers(map_object: folium.Map, scenario: dict, *, is_selected_pin: bool) -> None:
    center_lat, center_lon = scenario["scenario_center"]

    incident_layer = folium.FeatureGroup(
        name="SIMULATED SCENARIO POINT — NOT A DISPATCH",
        show=True,
    )
    if is_selected_pin:
        marker_title = "User-selected map pin (display only)"
        popup_text = (
            "User-selected pin used only for this local visual simulation. "
            "No real responder has been assigned or contacted."
        )
        folium.Marker(
            location=(center_lat, center_lon),
            tooltip=marker_title,
            popup=folium.Popup(popup_text, max_width=280),
            icon=folium.Icon(color="black", icon="map-pin", prefix="fa"),
        ).add_to(incident_layer)
    else:
        folium.CircleMarker(
            location=(center_lat, center_lon),
            radius=9,
            color="#333333",
            fill=True,
            fill_color="#f0f0f0",
            fill_opacity=1,
            tooltip="Fictional demo point — not a real incident",
            popup="Generic demonstration point; not a user location.",
        ).add_to(incident_layer)
    incident_layer.add_to(map_object)

    route_layer = folium.FeatureGroup(name="SIMULATED STRAIGHT-LINE ROUTES — NOT NAVIGATION", show=True)
    for route in scenario["routes"]:
        folium.PolyLine(
            locations=[route["start"], route["end"]],
            color={
                "SIM-MED-01": "#2471a3",
                "SIM-FIRE-01": "#c0392b",
                "SIM-RES-01": "#239b56",
                "SIM-SUP-01": "#7d3c98",
            }.get(route["resource_id"], "#555555"),
            weight=4,
            opacity=0.8,
            dash_array="8, 8",
            tooltip="SIMULATED STRAIGHT-LINE GEOMETRY — not a road route or driving directions",
            popup=(
                f"Illustrative straight-line distance: {route['distance_km']:.2f} km. "
                "No road route, travel time, ETA, or dispatch is calculated."
            ),
        ).add_to(route_layer)
    route_layer.add_to(map_object)

    resources_layer = folium.FeatureGroup(name="SYNTHETIC MOCK UNITS — NOT REAL RESPONDERS", show=True)
    for resource in scenario["resources"]:
        popup_html = (
            f"<b>{resource.resource_id}</b><br>"
            f"{resource.label}<br>"
            "SIMULATION ONLY — not a real vehicle, availability, or dispatch."
        )
        folium.Marker(
            location=(resource.latitude, resource.longitude),
            tooltip=f"{resource.resource_id} · {resource.resource_type} · SIMULATED",
            popup=folium.Popup(popup_html, max_width=300),
            icon=folium.Icon(color=resource.color, icon=resource.icon, prefix="fa"),
        ).add_to(resources_layer)
    resources_layer.add_to(map_object)

    folium.LayerControl(collapsed=False).add_to(map_object)


def render_simulation_map() -> None:
    """Render the map only when explicitly enabled by the visitor."""
    with st.expander("Explore simulated resource locations and route layers", expanded=False):
        st.warning(
            "SIMULATION ONLY — all resource markers are fictional. This view does not show live units, "
            "real availability, dispatch assignments, road navigation, travel times, or ETAs. "
            "Mock units are not selected or assigned based on your report."
        )
        st.caption(
            "No location is sent to a routing or geocoding API by this feature. Map tiles are still "
            "requested from OpenStreetMap when the map is displayed."
        )

        lat = st.session_state.get("selected_latitude")
        lon = st.session_state.get("selected_longitude")
        has_selected_pin = lat is not None and lon is not None
        use_selected_pin = st.checkbox(
            "Use my currently selected map pin for this simulation only (session display; not saved by this option)",
            key="simulation_use_selected_pin",
            disabled=not has_selected_pin,
        )
        show_map = st.checkbox(
            "Show simulated resource and route map",
            key="simulation_map_enabled",
        )
        if not show_map:
            st.caption("The map overlay stays hidden until you enable it above.")
            return

        use_selected_pin = bool(use_selected_pin and has_selected_pin)
        if use_selected_pin:
            center_lat, center_lon = float(lat), float(lon)
            zoom = 13
            st.info(
                "The selected pin is used only to draw this local demonstration. It does not submit, store, "
                "transmit to a routing provider, or dispatch anything by itself."
            )
        else:
            center_lat, center_lon = _DEMO_CENTER
            zoom = 13
            st.caption("Using a generic demo point in India, not your current location.")

        scenario = build_simulation_scenario(center_lat, center_lon)
        map_object = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=zoom,
            control_scale=True,
            tiles="OpenStreetMap",
        )
        _add_simulation_layers(map_object, scenario, is_selected_pin=use_selected_pin)
        st_folium(
            map_object,
            height=470,
            use_container_width=True,
            returned_objects=[],
            key="phase167_simulation_map",
        )
        st.caption(
            "Displayed route distances are great-circle approximations. Dashed lines are illustrative straight lines, "
            "not street paths. No ETA is calculated, and mock units are not associated with any real service."
        )

        with st.expander("Show mock unit legend and illustrative distances", expanded=False):
            for resource, route in zip(scenario["resources"], scenario["routes"]):
                st.write(
                    f"**{resource.resource_id} — {resource.resource_type}:** "
                    f"{route['distance_km']:.2f} km straight-line illustration."
                )
            st.caption("Distance is not driving distance, response time, or a resource availability signal.")
