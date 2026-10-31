"""Public incident intake with location, voice, AI preview, and Phase 16.9 protections.

This module writes a report only after explicit storage consent and only through the
PostgreSQL persistence module. It deliberately does not read/list reports or expose
operator-only functions.
"""

from __future__ import annotations

from datetime import datetime
import logging
import time
from typing import Any

import streamlit as st

from smartcity.config import get_secret, settings
from smartcity.abuse_protection import public_limit_message, reserve_action_slot
from smartcity.ui.location_helpers import prepare_required_consented_location
from smartcity.ui.location_picker import render_location_picker
from smartcity.ui.simulation_map import render_simulation_map
from smartcity.ui.intake_helpers import (
    effective_report_limit,
    safe_receipt_payload,
    validate_public_submission,
)
from smartcity.storage.postgres import create_public_report, is_database_configured
from smartcity.ui.voice_transcription import MAX_AUDIO_BYTES, transcribe_audio_bytes
from smartcity.agents.public_pipeline import (
    AgentPipelineConfigurationError,
    AgentPipelineExecutionError,
    run_public_agent_pipeline,
)

logger = logging.getLogger(__name__)
PENDING_AI_TTL_SECONDS = 15 * 60


def _effective_report_limit() -> int:
    return effective_report_limit(settings.max_report_chars)


def _set_submission_result(kind: str, **values: Any) -> None:
    st.session_state["public_intake_result"] = {"kind": kind, **values}


def _submit_report_callback() -> None:
    """Handle form submission before the next Streamlit render."""
    if not is_database_configured():
        _set_submission_result(
            "database_unconfigured",
            message="Report storage is not configured yet. Your report has not been submitted.",
        )
        return

    try:
        raw_text = st.session_state.get("report_text", "")
        report_text = validate_public_submission(
            raw_text,
            consent_to_store_report=st.session_state.get("consent_to_store_report", False),
            confirm_prototype_only=st.session_state.get("confirm_prototype_only", False),
            max_chars=_effective_report_limit(),
        )

        # A location is required for this prototype flow. The visitor may use GPS,
        # a map pin, manual coordinates, or an address/landmark label. Storage still
        # requires a separate explicit location-consent checkbox.
        try:
            location_payload = prepare_required_consented_location(
                latitude=st.session_state.get("selected_latitude"),
                longitude=st.session_state.get("selected_longitude"),
                location_label=st.session_state.get("location_label_input", ""),
                location_source=st.session_state.get("selected_location_source", "none"),
                consent_to_store_location=st.session_state.get("consent_to_store_location", False),
            )
        except ValueError as exc:
            _set_submission_result("validation_error", message=str(exc))
            return

        input_method = st.session_state.get("report_input_method", "text")
        if input_method not in {"text", "voice_transcription"}:
            input_method = "text"

        limit_decision = reserve_action_slot(st.session_state, "report_submit")
        if not limit_decision.allowed:
            kind = "protection_unavailable" if limit_decision.reason == "limiter_unavailable" else "rate_limited"
            _set_submission_result(kind, message=public_limit_message(limit_decision))
            return

        ai_consent = st.session_state.get("consent_to_ai_analysis", False) is True
        receipt = create_public_report(
            report_text,
            consent_to_store_report=True,
            input_method=input_method,
            **location_payload,
        )
        safe_receipt = safe_receipt_payload(receipt)
        _set_submission_result("success", receipt=safe_receipt)
        st.session_state.pop("public_ai_assessment", None)
        if ai_consent:
            # Keep the report text in session memory only until the user runs preview.
            # Do not send location, query other reports, or save the AI output to PostgreSQL.
            st.session_state["pending_ai_assessment"] = {
                "report_text": report_text,
                "reference_code": safe_receipt["reference_code"],
                "created_at_epoch": time.time(),
            }
        else:
            st.session_state.pop("pending_ai_assessment", None)
        # Callback executes before the next render, so resetting widget state is safe.
        st.session_state["report_text"] = ""
        st.session_state["report_input_method"] = "text"
        st.session_state["consent_to_store_report"] = False
        st.session_state["consent_to_ai_analysis"] = False
        st.session_state["confirm_prototype_only"] = False
        st.session_state["consent_to_send_audio"] = False
        st.session_state["voice_transcript"] = ""
        st.session_state["voice_transcript_applied"] = False
        st.session_state["voice_transcription_error"] = ""
        st.session_state["voice_widget_epoch"] = st.session_state.get("voice_widget_epoch", 0) + 1
        # Clear previously selected location so it cannot be attached to the next report.
        st.session_state["selected_latitude"] = None
        st.session_state["selected_longitude"] = None
        st.session_state["selected_location_source"] = "none"
        st.session_state["location_label_input"] = ""
        st.session_state["manual_lat_input"] = ""
        st.session_state["manual_lon_input"] = ""
        st.session_state["consent_to_store_location"] = False
        st.session_state["simulation_use_selected_pin"] = False
        st.session_state["location_picker_status"] = ""
        st.session_state["last_map_click"] = None
        st.session_state["location_map_epoch"] = st.session_state.get("location_map_epoch", 0) + 1
    except ValueError as exc:
        # Display only known validation messages; never surface unexpected internals.
        known_messages = {
            "Please confirm that this is a prototype and not an emergency-service channel.",
            "Report storage consent is required before submitting.",
            "Enter a brief description before submitting.",
        }
        if str(exc) in known_messages:
            _set_submission_result("validation_error", message=str(exc))
        else:
            _set_submission_result(
                "storage_error",
                message=(
                    "We could not confirm that your report was saved. This prototype is not an "
                    "emergency-service channel. If this is an immediate emergency in India, call 112."
                ),
            )
    except Exception:
        # Do not log report text, location, DSN, or raw database exception details.
        logger.warning("public_report_storage_failed")
        _set_submission_result(
            "storage_error",
            message=(
                "We could not confirm that your report was saved. This prototype is not an "
                "emergency-service channel. If this is an immediate emergency in India, call 112."
            ),
        )


def _use_reviewed_transcript_callback() -> None:
    """Copy the user's editable transcript into the report field, without submitting it."""
    transcript = st.session_state.get("voice_transcript", "")
    if not isinstance(transcript, str) or not transcript.strip():
        st.session_state["voice_transcription_error"] = (
            "The transcript is empty. Record or edit a short report before using it."
        )
        return

    st.session_state["report_text"] = transcript[:_effective_report_limit()]
    st.session_state["report_input_method"] = "voice_transcription"
    st.session_state["voice_transcript_applied"] = True
    st.session_state["voice_transcription_error"] = ""
    # The transcript is not submitted here. The user must still submit the form
    # and affirm both report-storage and prototype-only consent.
    st.session_state.pop("public_intake_result", None)


def _render_voice_input(limit: int) -> None:
    """Offer optional voice-to-text and always show a transcript editor after recording.

    Recording alone does not reveal words: speech-to-text must run first. To preserve
    explicit consent, audio is sent to Groq only after the user checks the consent box
    and clicks the transcription button. Raw audio is never persisted by this app.
    """
    st.subheader("Or record a voice report")
    st.caption(
        "Record your description, convert it into text, then review and edit the words "
        "before using them in your report. Raw audio is not written to the database or files."
    )
    st.info(
        "Privacy notice: when you explicitly choose **Transcribe recording**, the recording is "
        "sent to the configured Groq speech-to-text API. Avoid unnecessary names, phone numbers, "
        "or other personal details."
    )

    api_key = get_secret("GROQ_API_KEY")
    st.checkbox(
        "I consent to sending this recording to Groq for speech-to-text transcription.",
        key="consent_to_send_audio",
    )
    language_options = {
        "Auto-detect": None,
        "English": "en",
        "Hindi": "hi",
        "Punjabi": "pa",
        "Urdu": "ur",
    }
    selected_language = st.selectbox(
        "Spoken language",
        options=list(language_options.keys()),
        index=0,
        key="voice_language_choice",
        help="Choose the language spoken in the recording, or leave Auto-detect selected.",
    )

    epoch = int(st.session_state.get("voice_widget_epoch", 0))
    audio_file = st.audio_input(
        "Record a short incident description",
        sample_rate=16000,
        key=f"voice_recording_{epoch}",
        help="After recording, click Convert recording to text. The resulting words will appear in the transcript box below.",
    )

    oversized = bool(audio_file and getattr(audio_file, "size", 0) > MAX_AUDIO_BYTES)
    if oversized:
        st.warning(
            f"This recording exceeds the {MAX_AUDIO_BYTES // (1024 * 1024)} MiB limit. "
            "Record a shorter description and try again."
        )
    elif audio_file is not None:
        st.success(
            f"Recording ready ({getattr(audio_file, 'size', 0):,} bytes). "
            "Next, convert it to text to see what was spoken."
        )

    if not api_key:
        st.markdown(
            '<div class="service-note"><strong>Speech-to-text is not configured</strong><br>'
            'The recording can be captured, but it cannot be converted into words until the app owner '
            'adds a valid GROQ_API_KEY in Streamlit Cloud → Manage app → Settings → Secrets. '
            'You can still type or paste the wording into the transcript box.</div>',
            unsafe_allow_html=True,
        )

    transcribe_clicked = st.button(
        "✦  Convert recording to text",
        key="transcribe_voice_button",
        type="primary",
        use_container_width=True,
        disabled=(
            audio_file is None
            or oversized
            or not bool(api_key)
            or not st.session_state.get("consent_to_send_audio", False)
        ),
        help=(
            "Requires a recording, a configured Groq API key, and your transcription consent."
        ),
    )
    if transcribe_clicked:
        # Clear any older transcript so a failed new attempt cannot leave stale words.
        st.session_state["voice_transcript"] = ""
        st.session_state["voice_transcript_applied"] = False
        limit_decision = reserve_action_slot(st.session_state, "audio_transcription")
        if not limit_decision.allowed:
            st.session_state["voice_transcription_error"] = public_limit_message(limit_decision)
            logger.warning("voice_transcription_action_blocked reason=%s", limit_decision.reason)
        else:
            try:
                transcript = transcribe_audio_bytes(
                    audio_file.getvalue(),
                    getattr(audio_file, "type", None),
                    consent_to_transcribe=st.session_state.get("consent_to_send_audio", False),
                    api_key=api_key,
                    language=language_options[selected_language],
                )
                st.session_state["voice_transcript"] = transcript[:limit]
                st.session_state["voice_transcription_error"] = ""
                st.session_state["voice_transcript_applied"] = False
                # Clear the recording widget after successful transcription; keep only text.
                st.session_state["voice_widget_epoch"] = epoch + 1
            except (ValueError, RuntimeError) as exc:
                st.session_state["voice_transcription_error"] = str(exc)
                logger.warning("voice_transcription_failed category=%s", type(exc).__name__)
            except Exception:
                logger.warning("voice_transcription_failed category=unexpected")
                st.session_state["voice_transcription_error"] = (
                    "Transcription failed unexpectedly. Check the API configuration and try again."
                )

    transcription_error = st.session_state.get("voice_transcription_error", "")
    if transcription_error:
        st.warning(transcription_error)

    # Show the transcript box immediately after capture, rather than hiding it until
    # a transcript exists. It becomes populated after the explicit transcription action.
    if audio_file is not None or st.session_state.get("voice_transcript", ""):
        st.markdown("**Your spoken words · transcript preview**")
        if st.session_state.get("voice_transcript", ""):
            transcript_placeholder = "Your transcription will appear here. You can correct it before using it."
            transcript_help = "Review the recognized words and correct any mistakes before copying them into the incident description."
        else:
            transcript_placeholder = (
                "Your spoken words will appear here after you click ‘Convert recording to text’. "
                "You can also type the wording manually."
            )
            transcript_help = (
                "This box appears as soon as a recording is captured. To fill it automatically, "
                "configure GROQ_API_KEY, keep transcription consent checked, and click Convert recording to text."
            )

        st.text_area(
            "Transcript (editable)",
            key="voice_transcript",
            max_chars=limit,
            height=135,
            placeholder=transcript_placeholder,
            help=transcript_help,
        )
        transcript_ready = bool(str(st.session_state.get("voice_transcript", "")).strip())
        st.button(
            "Use this text in the incident description",
            key="use_voice_transcript_button",
            on_click=_use_reviewed_transcript_callback,
            use_container_width=True,
            disabled=not transcript_ready,
        )
        if st.session_state.get("voice_transcript_applied"):
            st.success(
                "Text copied into the incident description. Review it there before submitting."
            )


def _render_result() -> None:
    result = st.session_state.get("public_intake_result")
    if not result:
        return

    kind = result.get("kind")
    if kind == "success":
        receipt = result["receipt"]
        st.success("Your report was recorded in the prototype database.")
        st.markdown("#### Your reference code")
        st.code(receipt["reference_code"], language=None)
        submitted_at = receipt.get("submitted_at")
        if isinstance(submitted_at, datetime):
            submitted_at_text = submitted_at.astimezone().strftime("%d %b %Y, %I:%M:%S %p %Z")
        else:
            submitted_at_text = str(submitted_at or "Not available")
        st.caption(f"Recorded at: {submitted_at_text}")
        st.info(
            "This reference confirms only that the prototype stored a report. It does not "
            "mean that an operator reviewed it, emergency services were contacted, or help is on the way."
        )
    elif kind == "validation_error":
        st.warning(result.get("message", "Please check your entries."))
    elif kind == "database_unconfigured":
        st.warning(result.get("message", "Report storage is not configured."))
    elif kind == "storage_error":
        st.error(result.get("message", "Report storage could not be confirmed."))
    elif kind == "rate_limited":
        st.warning(result.get("message", "Too many requests. Please wait before trying again."))
    elif kind == "protection_unavailable":
        st.error(result.get("message", "Request protection is temporarily unavailable."))

    if kind == "success":
        _render_ai_assessment_preview()


def _render_ai_assessment_preview() -> None:
    """Offer a second, explicit AI step; this never creates a dispatch or DB update."""
    pending = st.session_state.get("pending_ai_assessment")
    completed = st.session_state.get("public_ai_assessment")

    if pending:
        created_at = pending.get("created_at_epoch")
        if not isinstance(created_at, (int, float)) or time.time() - float(created_at) > PENDING_AI_TTL_SECONDS:
            st.session_state.pop("pending_ai_assessment", None)
            pending = None
            st.info("The temporary AI-preview window expired. Your stored report remains unchanged; no AI assessment was run.")

    if completed:
        completed_at = completed.get("completed_at_epoch")
        if not isinstance(completed_at, (int, float)) or time.time() - float(completed_at) > PENDING_AI_TTL_SECONDS:
            st.session_state.pop("public_ai_assessment", None)
            completed = None
            st.info("The temporary AI-preview result expired from this session. The stored report remains unchanged.")

    if completed:
        assessment = completed.get("assessment", {})
        st.markdown("#### AI assessment preview — not a dispatch decision")
        engine = completed.get("engine", "unknown")
        if engine == "phase1_15_adapter":
            st.caption("Engine: exported Phase 1–15 adapter")
        else:
            st.caption("Engine: Groq structured compatibility assessment (not the original Phase 1–15 graph)")
        urgency = assessment.get("urgency", "uncertain")
        st.metric("Preliminary urgency", str(urgency).replace("_", " ").title())
        st.write("**Incident category:**", str(assessment.get("incident_type", "unclear")).replace("_", " ").title())
        st.write("**Summary:**", assessment.get("summary", "No summary available."))
        st.write("**Why this classification:**", assessment.get("triage_reason", "Human review is required."))
        st.write("**People potentially at risk:**", assessment.get("people_at_risk", "Unclear from report."))
        hazards = assessment.get("hazards", [])
        if hazards:
            st.write("**Possible hazards:**", ", ".join(str(item) for item in hazards))
        confidence = assessment.get("confidence")
        if isinstance(confidence, (float, int)):
            st.caption(f"Model-reported confidence: {confidence:.0%}. This is not a calibrated probability.")
        st.warning(
            "This output can be wrong and requires human review. It does not contact emergency services, "
            "approve an assignment, reserve a resource, or mean help is on the way. For immediate danger in India, call 112."
        )
        return

    if not pending:
        return

    st.markdown("#### Optional AI assessment preview")
    st.caption(
        f"The report {pending.get('reference_code', '')} is stored. Clicking the button sends only its report text "
        "to the configured AI model; location is not sent. The assessment is not saved to the database."
    )
    if st.button("Run AI assessment preview", key="run_public_ai_assessment", type="secondary"):
        limit_decision = reserve_action_slot(st.session_state, "ai_assessment")
        if not limit_decision.allowed:
            logger.warning("ai_assessment_action_blocked reason=%s", limit_decision.reason)
            if limit_decision.reason == "limiter_unavailable":
                st.error(public_limit_message(limit_decision))
            else:
                st.warning(public_limit_message(limit_decision))
            return
        try:
            result = run_public_agent_pipeline(
                pending.get("report_text", ""),
                consent_to_ai_analysis=True,
                api_key=get_secret("GROQ_API_KEY"),
                model=get_secret("AGENT_MODEL", "openai/gpt-oss-120b") or "openai/gpt-oss-120b",
            )
            result["completed_at_epoch"] = time.time()
            st.session_state["public_ai_assessment"] = result
            # Remove report text from session state once analysis succeeds.
            st.session_state.pop("pending_ai_assessment", None)
            st.rerun()
        except AgentPipelineConfigurationError as exc:
            logger.warning("ai_assessment_failed category=configuration")
            st.warning(str(exc))
        except (AgentPipelineExecutionError, ValueError) as exc:
            logger.warning("ai_assessment_failed category=%s", type(exc).__name__)
            st.warning(
                "The AI assessment could not be completed. Your report remains stored; no dispatch occurred. "
                "You can retry after checking the app configuration."
            )
        except Exception:
            logger.warning("ai_assessment_failed category=unexpected")
            st.warning(
                "The AI assessment could not be completed. Your report remains stored; no dispatch occurred."
            )


def render_public_intake() -> None:
    """Render the ordered public flow: describe, voice, locate, then submit."""
    limit = _effective_report_limit()

    st.markdown(
        '<div class="section-kicker">Step 1 · Incident details</div>'
        '<div class="section-title">Tell us what happened</div>'
        '<div class="section-description">Describe the incident in your own words, or record a voice report below. Use fictional data while testing.</div>',
        unsafe_allow_html=True,
    )
    st.text_area(
        "Incident description",
        key="report_text",
        max_chars=limit,
        height=150,
        placeholder=(
            "Example for testing: Smoke is visible near the entrance of a fictional building. "
            "No real responders will be contacted."
        ),
        help=(
            f"Maximum {limit} characters. Correct transcription errors and do not include "
            "passwords or unrelated personal information."
        ),
    )
    _render_voice_input(limit)

    st.divider()
    render_location_picker()
    render_simulation_map()

    st.divider()
    st.markdown(
        '<div class="section-kicker">Step 3 · Confirmation</div>'
        '<div class="section-title">Review and submit the report</div>'
        '<div class="section-description">Confirm how the report may be stored. Location is required and has a separate consent check.</div>',
        unsafe_allow_html=True,
    )

    database_ready = is_database_configured()
    selected_latitude = st.session_state.get("selected_latitude")
    selected_longitude = st.session_state.get("selected_longitude")
    entered_location_label = str(st.session_state.get("location_label_input", "") or "").strip()
    location_available = (
        selected_latitude is not None and selected_longitude is not None
    ) or bool(entered_location_label)
    location_consent = st.session_state.get("consent_to_store_location", False) is True
    submission_ready = database_ready and location_available and location_consent

    if not database_ready:
        st.markdown(
            '<div class="service-note"><strong>Report storage is not available yet</strong><br>'
            'This demo is still being configured, so submissions are disabled and no report can be saved right now.</div>',
            unsafe_allow_html=True,
        )
    elif not location_available:
        st.info("Add your current location, place a map pin, or enter an address/landmark to continue.")
    elif not location_consent:
        st.info("Please check the separate location-storage consent above to enable report submission.")

    with st.form("public_incident_intake", clear_on_submit=False, border=True):
        st.checkbox(
            "I consent to storing this incident description in the prototype database.",
            key="consent_to_store_report",
        )
        st.checkbox(
            "Optional: I consent to sending this report text to the configured AI model for a non-binding assessment preview.",
            key="consent_to_ai_analysis",
            help="This is separate from storage consent. The preview is not emergency assistance and will not trigger dispatch.",
        )
        st.checkbox(
            "I understand this is a demonstration and does not contact emergency services or dispatch responders.",
            key="confirm_prototype_only",
        )
        st.form_submit_button(
            "Submit demonstration report",
            type="primary",
            use_container_width=True,
            disabled=not submission_ready,
            on_click=_submit_report_callback,
        )

    _render_result()


def render_public_intake_limitations() -> None:
    """Render privacy and prototype details at the bottom of the public page."""
    with st.expander("What this form does and does not do", expanded=False):
        st.markdown(
            """
            - It stores report text only after explicit report-storage consent.
            - A location is required to submit. Location/address details are stored only after separate location consent.
            - Voice audio is sent to Groq only after separate transcription consent and an explicit button click; the app does not store raw audio.
            - Only reviewed transcript text can be submitted to PostgreSQL, and only after report-storage consent.
            - A non-binding AI assessment preview is optional and requires separate consent plus a button click.
            - AI output is held in session memory only; this phase does not persist assessment output.
            - It does not approve assignments, reserve resources, or dispatch a responder.
            - A reference code is a storage receipt, not proof of emergency assistance.
            """
        )

    with st.expander("Privacy, storage and prototype limitations", expanded=False):
        st.markdown(
            """
            - Reports are stored only after explicit report-storage consent.
            - Location is required for submission and saved only after separate location consent.
            - Voice audio is sent to Groq only after explicit transcription consent and a button click; raw audio is not saved by this app.
            - AI assessment previews are optional and non-binding. They are not dispatch decisions.
            - Request throttling is session-based, not IP-wide; reports do not yet have an automatic retention schedule.
            - A reference code confirms storage only. It does not mean that anyone has reviewed the report or that help is on the way.
            """
        )
