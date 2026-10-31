"""Required location selection with browser GPS, map pin, and manual fallbacks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import folium
import streamlit as st
import streamlit.components.v1 as components
from streamlit_folium import st_folium

from smartcity.ui.location_helpers import parse_optional_coordinate_pair

_DEFAULT_CENTER = (22.9734, 78.6569)  # Generic map center for India; not user location.
_COMPONENT_DIR = Path(__file__).resolve().parent / "browser_location_component"
_browser_location = components.declare_component(
    "smartcity_browser_location",
    path=str(_COMPONENT_DIR),
)

_STATE_DEFAULTS = {
    "selected_latitude": None,
    "selected_longitude": None,
    "selected_location_source": "none",
    "location_label_input": "",
    "manual_lat_input": "",
    "manual_lon_input": "",
    "consent_to_store_location": False,
    "location_picker_status": "",
    "last_browser_location_result": None,
    "last_map_click": None,
    "location_map_epoch": 0,
}


def _initialize_state() -> None:
    for key, value in _STATE_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _apply_browser_location(result: Any) -> None:
    if not isinstance(result, dict) or result == st.session_state.get("last_browser_location_result"):
        return
    if result.get("status") not in {"success", "error"}:
        return
    st.session_state["last_browser_location_result"] = result
    if result.get("status") == "error":
        st.session_state["location_picker_status"] = str(
            result.get("message", "Location unavailable. Choose a map pin or enter a landmark instead.")
        )
        return

    try:
        lat, lon = parse_optional_coordinate_pair(result.get("latitude"), result.get("longitude"))
    except ValueError:
        st.session_state["location_picker_status"] = (
            "The browser returned invalid coordinates. Please choose another location."
        )
        return
    if lat is None or lon is None:
        st.session_state["location_picker_status"] = "The browser did not return a complete coordinate pair."
        return

    st.session_state["selected_latitude"] = lat
    st.session_state["selected_longitude"] = lon
    st.session_state["selected_location_source"] = "gps"
    st.session_state["simulation_use_selected_pin"] = False
    accuracy = result.get("accuracy_m")
    accuracy_text = (
        f" Approximate browser accuracy: {accuracy:.0f} m."
        if isinstance(accuracy, (float, int)) else ""
    )
    st.session_state["location_picker_status"] = (
        f"Current location selected.{accuracy_text} Please review the pin and consent before submitting."
    )


def _render_manual_coordinates() -> None:
    with st.expander("Enter coordinates manually", expanded=False):
        st.caption("Use decimal degrees. For example, a fictional Delhi test point could be 28.6139, 77.2090.")
        with st.form("manual_location_coordinates", border=False):
            left, right = st.columns(2)
            with left:
                st.text_input("Latitude", key="manual_lat_input", placeholder="e.g. 28.6139")
            with right:
                st.text_input("Longitude", key="manual_lon_input", placeholder="e.g. 77.2090")
            submitted = st.form_submit_button("Use these coordinates", use_container_width=True)

        if submitted:
            try:
                lat, lon = parse_optional_coordinate_pair(
                    st.session_state.get("manual_lat_input"),
                    st.session_state.get("manual_lon_input"),
                )
                if lat is None or lon is None:
                    raise ValueError("Enter both latitude and longitude.")
                st.session_state["selected_latitude"] = lat
                st.session_state["selected_longitude"] = lon
                st.session_state["selected_location_source"] = "manual"
                st.session_state["simulation_use_selected_pin"] = False
                st.session_state["location_picker_status"] = (
                    "Manual coordinates selected. Review the pin and consent before submitting."
                )
                st.rerun()
            except ValueError as exc:
                st.session_state["location_picker_status"] = str(exc)


def _render_map() -> None:
    lat = st.session_state.get("selected_latitude")
    lon = st.session_state.get("selected_longitude")
    has_pin = lat is not None and lon is not None
    center = (float(lat), float(lon)) if has_pin else _DEFAULT_CENTER
    incident_map = folium.Map(
        location=center,
        zoom_start=14 if has_pin else 5,
        control_scale=True,
        tiles="OpenStreetMap",
    )
    if has_pin:
        folium.Marker(
            location=(float(lat), float(lon)),
            tooltip="Selected incident location",
            popup=(
                "Selected location for this prototype report; "
                "not a dispatched responder."
            ),
            icon=folium.Icon(color="red", icon="info-sign"),
        ).add_to(incident_map)

    st.caption(
        "Or click the map to place or move the required location pin. "
        "The initial view is a generic map center for India, not your current position."
    )
    result = st_folium(
        incident_map,
        height=340,
        use_container_width=True,
        returned_objects=["last_clicked"],
        key=f"incident_location_map_{st.session_state.get('location_map_epoch', 0)}",
    )
    clicked = result.get("last_clicked") if isinstance(result, dict) else None
    if isinstance(clicked, dict) and clicked.get("lat") is not None and clicked.get("lng") is not None:
        try:
            lat_clicked, lon_clicked = parse_optional_coordinate_pair(clicked["lat"], clicked["lng"])
            click_key = (round(lat_clicked, 7), round(lon_clicked, 7))
            if click_key != st.session_state.get("last_map_click"):
                st.session_state["last_map_click"] = click_key
                st.session_state["selected_latitude"] = lat_clicked
                st.session_state["selected_longitude"] = lon_clicked
                st.session_state["selected_location_source"] = "manual"
                st.session_state["simulation_use_selected_pin"] = False
                st.session_state["location_picker_status"] = (
                    "Map pin selected. Review the position and consent before submitting."
                )
                st.rerun()
        except (TypeError, ValueError):
            st.session_state["location_picker_status"] = (
                "The map returned an invalid position. Please select the pin again."
            )


def render_location_picker() -> None:
    """Render a required location step with GPS as the prominent first action."""
    _initialize_state()
    st.markdown(
        """
        <div class="location-step-heading">
          <div class="section-kicker">Step 2 · Incident location <span class="required-chip">REQUIRED</span></div>
          <div class="section-title">Where is it happening?</div>
          <div class="section-description">Choose your current position, place a map pin, or enter a nearby address or landmark.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        st.markdown(
            '<div class="location-action-title">📍 Share the incident location</div>'
            '<div class="location-action-copy">The browser asks permission before reading your location. You can use the map or enter a landmark instead.</div>',
            unsafe_allow_html=True,
        )
        gps_result = _browser_location(key="browser_location_request", default={"status": "idle"})
        _apply_browser_location(gps_result)

        st.text_input(
            "Address or landmark",
            key="location_label_input",
            max_chars=250,
            placeholder="e.g. Near Gate 2, Sector 63, Noida",
            help="You may enter a nearby address or landmark instead of coordinates. It is stored only with your location consent.",
        )
        _render_manual_coordinates()
        st.markdown("**Or choose the exact point on the map**")
        _render_map()

        lat = st.session_state.get("selected_latitude")
        lon = st.session_state.get("selected_longitude")
        label = str(st.session_state.get("location_label_input", "") or "").strip()
        has_coordinates = lat is not None and lon is not None
        if has_coordinates:
            st.success(
                f"Location selected · {float(lat):.6f}, {float(lon):.6f} · "
                f"Source: {st.session_state.get('selected_location_source', 'manual')}"
            )
        elif label:
            st.success("Address or landmark entered. This will be used as the report location.")
        else:
            st.warning("Location is required before you can submit this report.")

        if st.session_state.get("location_picker_status"):
            st.info(st.session_state["location_picker_status"])

        st.checkbox(
            "I consent to storing this location or address with my report. (Required)",
            key="consent_to_store_location",
        )
        st.caption(
            "Your location is not stored unless you check this box. GPS sharing sends coordinates to this app session for display; "
            "the coordinates or address are saved with the report only after your consent and successful submission."
        )
