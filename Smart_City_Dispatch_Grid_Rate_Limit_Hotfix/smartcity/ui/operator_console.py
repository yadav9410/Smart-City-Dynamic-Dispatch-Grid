"""Authenticated operator console for reviewing public prototype reports."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from smartcity.operator_auth import (
    LOGIN_LOCKOUT_SECONDS,
    MAX_LOGIN_ATTEMPTS_PER_SESSION,
    get_operator_password_hash,
    is_operator_auth_configured,
    verify_operator_password,
)


def _format_timestamp(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return str(value or "—")


def _operator_login(st) -> bool:
    """Render login form and return true only after password verification."""
    import time

    if not is_operator_auth_configured():
        st.error("Operator access is not configured. The console is locked.")
        st.markdown(
            "Configure `OPERATOR_PASSWORD_HASH` in deployment secrets. Generate a hash "
            "locally with `python -m smartcity.operator_auth`; never use a plaintext "
            "operator password in source code."
        )
        return False

    lockout_until = float(st.session_state.get("operator_lockout_until", 0) or 0)
    now = time.time()
    if now < lockout_until:
        remaining = max(1, int(lockout_until - now))
        st.warning(f"Login temporarily locked after repeated failures. Try again in about {remaining} seconds.")
        return False

    st.subheader("Operator sign-in")
    st.caption("This workspace is separate from public report submission.")
    with st.form("operator_login_form", clear_on_submit=True):
        password = st.text_input("Operator password", type="password", autocomplete="current-password")
        submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)

    if submitted:
        stored_hash = get_operator_password_hash()
        if verify_operator_password(password, stored_hash):
            st.session_state["operator_authenticated"] = True
            st.session_state["operator_last_activity"] = time.time()
            st.session_state.pop("operator_session_expired", None)
            st.session_state["operator_failed_attempts"] = 0
            st.session_state["operator_lockout_until"] = 0
            st.rerun()
        else:
            failures = int(st.session_state.get("operator_failed_attempts", 0) or 0) + 1
            if failures >= MAX_LOGIN_ATTEMPTS_PER_SESSION:
                st.session_state["operator_failed_attempts"] = 0
                st.session_state["operator_lockout_until"] = time.time() + LOGIN_LOCKOUT_SECONDS
                st.warning("Login temporarily locked after repeated failures. Try again later.")
            else:
                st.session_state["operator_failed_attempts"] = failures
                st.error("Unable to authenticate operator. Check credentials and try again.")
    return False


def render_operator_console() -> None:
    """Render report list and review actions only after operator authentication."""
    import streamlit as st

    from smartcity.storage.postgres import (
        ALLOWED_STATUS_TRANSITIONS,
        VALID_STATUSES,
        is_database_configured,
        list_audit_events,
        list_public_reports,
        update_public_report_status,
    )

    st.title("🔐 Protected Operator Console")
    st.warning(
        "Internal workflow review only. Status changes do not dispatch responders, "
        "reserve resources, or contact emergency services."
    )

    if st.session_state.pop("operator_session_expired", False):
        st.info("Your operator session expired after inactivity. Please sign in again.")

    if st.session_state.get("operator_authenticated") is not True:
        _operator_login(st)
        return

    import time

    st.caption("Authenticated operator session · 15-minute inactivity timeout")
    top_left, top_right = st.columns([4, 1])
    with top_left:
        st.caption("Report content and consented location are sensitive. Open them only when needed.")
    with top_right:
        if st.button("Log out", use_container_width=True):
            for key in (
                "operator_authenticated",
                "operator_last_activity",
                "operator_session_expired",
            ):
                st.session_state.pop(key, None)
            st.rerun()

    if not is_database_configured():
        st.error("Database storage is not configured. Report records cannot be loaded.")
        return

    filter_options = ["All statuses", *sorted(VALID_STATUSES)]
    filter_col, limit_col = st.columns([3, 1])
    with filter_col:
        status_filter = st.selectbox("Filter by internal status", filter_options, key="operator_status_filter")
    with limit_col:
        limit = st.selectbox("Recent reports", [25, 50, 100, 200], index=1, key="operator_report_limit")

    try:
        reports = list_public_reports(
            limit=int(limit),
            status=None if status_filter == "All statuses" else status_filter,
        )
    except Exception:
        st.error("Could not load reports. Check database availability and operator configuration.")
        return

    st.metric("Reports in current view", len(reports))
    if not reports:
        st.info("No reports match the selected filter.")
        return

    summary_rows = []
    for report in reports:
        has_location = bool(report.get("location_consent")) and (
            report.get("latitude") is not None or report.get("location_label")
        )
        summary_rows.append(
            {
                "Reference": report.get("reference_code", ""),
                "Status": report.get("status", ""),
                "Submitted (UTC)": _format_timestamp(report.get("submitted_at")),
                "Input": report.get("input_method", ""),
                "Location shared": "Yes" if has_location else "No",
            }
        )
    st.dataframe(summary_rows, use_container_width=True, hide_index=True)

    reference_codes = [str(report.get("reference_code", "")) for report in reports]
    if st.session_state.get("operator_selected_reference") not in reference_codes:
        # Reset a stale selection if the operator changes the status filter.
        st.session_state["operator_selected_reference"] = reference_codes[0]
    selected_reference = st.selectbox(
        "Select a report to review",
        reference_codes,
        format_func=lambda ref: f"{ref} · {next((r.get('status', '') for r in reports if r.get('reference_code') == ref), '')}",
        key="operator_selected_reference",
    )
    report = next((r for r in reports if r.get("reference_code") == selected_reference), None)
    if report is None:
        st.error("Selected report is no longer available in this view. Refresh the list.")
        return

    st.divider()
    st.subheader(f"Report {report['reference_code']}")
    col1, col2, col3 = st.columns(3)
    col1.metric("Current status", str(report.get("status", "unknown")))
    col2.metric("Input method", str(report.get("input_method", "unknown")))
    col3.metric("Submitted (UTC)", _format_timestamp(report.get("submitted_at")))

    st.text_area(
        "Stored report text (authorized operator view)",
        value=str(report.get("report_text", "")),
        height=160,
        disabled=True,
        key=f"operator_report_text_{report['reference_code']}",
    )

    if report.get("location_consent") and (
        report.get("latitude") is not None
        or report.get("longitude") is not None
        or report.get("location_label")
    ):
        st.markdown("**Location shared by reporter**")
        if report.get("location_label"):
            st.write(f"Address / landmark: {report['location_label']}")
        if report.get("latitude") is not None and report.get("longitude") is not None:
            st.write(f"Coordinates: {float(report['latitude']):.6f}, {float(report['longitude']):.6f}")
        st.caption("Location is shown because the reporter consented to store it.")
    else:
        st.caption("No location was shared for this report, or location storage was not consented to.")

    allowed_next = sorted(ALLOWED_STATUS_TRANSITIONS.get(str(report.get("status")), frozenset()))
    st.subheader("Human review and internal status")
    if not allowed_next:
        st.info("This report has no further allowed status transitions.")
    else:
        with st.form(f"operator_status_form_{report['reference_code']}"):
            new_status = st.selectbox("Set internal status", allowed_next, key=f"operator_new_status_{report['reference_code']}")
            confirm_change = st.checkbox(
                "I confirm this is an internal workflow status change, not a dispatch action.",
                key=f"operator_confirm_status_{report['reference_code']}",
            )
            change_submitted = st.form_submit_button(
                "Save review status", type="primary", disabled=not confirm_change
            )
        if change_submitted and confirm_change:
            try:
                update_public_report_status(
                    str(report["reference_code"]), str(new_status), actor_role="operator"
                )
            except LookupError:
                st.error("Report not found. Refresh the report list.")
            except ValueError as exc:
                # Expected transition validation only; no SQL or internal details are shown.
                st.error(f"Status was not changed: {exc}")
            except Exception:
                st.error("Status update could not be confirmed. Check database availability.")
            else:
                st.success("Internal review status updated. No dispatch was initiated.")
                st.rerun()

    st.subheader("Audit history")
    try:
        audit_events = list_audit_events(reference_code=str(report["reference_code"]), limit=20)
    except Exception:
        st.warning("Audit history is temporarily unavailable.")
    else:
        if not audit_events:
            st.caption("No audit events found for this report.")
        else:
            audit_rows = [
                {
                    "Time (UTC)": _format_timestamp(event.get("created_at")),
                    "Event": event.get("event_type", ""),
                    "Actor role": event.get("actor_role", ""),
                    "Metadata": str(event.get("metadata", {})),
                }
                for event in audit_events
            ]
            st.dataframe(audit_rows, use_container_width=True, hide_index=True)

    st.caption(
        "Prototype limitation: this console uses one shared operator credential and a "
        "per-session best-effort login throttle. Use a managed identity provider, individual "
        "operator accounts, durable rate limiting, and stronger operational controls before "
        "handling real emergency or sensitive personal data."
    )
