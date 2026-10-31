"""Voice-to-text helpers for Phase 16.5.

Raw audio is validated in memory and sent to the configured Groq transcription API
only after the UI receives explicit user consent and an explicit button click. This
module never writes audio to disk or to PostgreSQL.
"""

from __future__ import annotations

from typing import Optional

from smartcity.safety import normalize_report_text
from smartcity.storage.postgres import MAX_REPORT_CHARS

DEFAULT_TRANSCRIPTION_MODEL = "whisper-large-v3-turbo"
# Keep audio below Streamlit maxUploadSize (10 MiB), leaving space for message overhead.
MAX_AUDIO_BYTES = 8 * 1024 * 1024

_SUPPORTED_AUDIO_TYPES = {
    "audio/wav": ("wav", "audio/wav"),
    "audio/x-wav": ("wav", "audio/wav"),
    "audio/wave": ("wav", "audio/wav"),
    "audio/webm": ("webm", "audio/webm"),
    "audio/ogg": ("ogg", "audio/ogg"),
    "audio/mp4": ("mp4", "audio/mp4"),
    "audio/mpeg": ("mp3", "audio/mpeg"),
    "audio/mp3": ("mp3", "audio/mpeg"),
    "audio/flac": ("flac", "audio/flac"),
    "audio/x-flac": ("flac", "audio/flac"),
}


def prepare_audio_payload(
    audio_bytes: bytes,
    content_type: Optional[str],
    *,
    max_bytes: int = MAX_AUDIO_BYTES,
) -> tuple[str, bytes, str]:
    """Validate audio bytes/type and return a safe filename, bytes, and MIME type."""
    if not isinstance(audio_bytes, (bytes, bytearray, memoryview)) or not audio_bytes:
        raise ValueError("Record a short voice report before transcribing.")

    payload = bytes(audio_bytes)
    if len(payload) > max_bytes:
        raise ValueError(
            f"Recording is too large. Keep it under {max_bytes // (1024 * 1024)} MiB and try again."
        )

    normalized_type = (content_type or "audio/wav").split(";", 1)[0].strip().lower()
    format_info = _SUPPORTED_AUDIO_TYPES.get(normalized_type)
    if not format_info:
        raise ValueError(
            "This recording format is not supported. Try recording again in your browser."
        )

    extension, mime_type = format_info
    return f"voice_report.{extension}", payload, mime_type


def transcribe_audio_bytes(
    audio_bytes: bytes,
    content_type: Optional[str],
    *,
    consent_to_transcribe: bool = False,
    api_key: Optional[str],
    language: Optional[str] = None,
    model: str = DEFAULT_TRANSCRIPTION_MODEL,
    max_bytes: int = MAX_AUDIO_BYTES,
) -> str:
    """Transcribe audio through Groq and return bounded, normalized editable text.

    No raw audio is written to disk, logged, or saved to the database by this helper.
    The caller is responsible for collecting explicit consent before calling it.
    """
    if consent_to_transcribe is not True:
        raise ValueError("Explicit consent to send the recording for transcription is required.")

    filename, payload, mime_type = prepare_audio_payload(
        audio_bytes, content_type, max_bytes=max_bytes
    )
    if not api_key or not api_key.strip():
        raise RuntimeError("Voice transcription is not configured. Add GROQ_API_KEY to secrets.")
    if model not in {"whisper-large-v3-turbo", "whisper-large-v3"}:
        raise ValueError("Unsupported transcription model configured.")

    try:
        from groq import Groq
    except ImportError as exc:
        raise RuntimeError(
            "The Groq SDK is missing. Install the project's requirements.txt first."
        ) from exc

    client = Groq(api_key=api_key.strip(), timeout=30.0, max_retries=1)
    request = {
        "file": (filename, payload, mime_type),
        "model": model,
        "response_format": "json",
        "temperature": 0.0,
    }
    if language and language.strip().lower() not in {"auto", "auto-detect", ""}:
        request["language"] = language.strip().lower()

    try:
        response = client.audio.transcriptions.create(**request)
    except Exception as exc:
        # Avoid surfacing SDK errors, request metadata, or credentials in the UI.
        raise RuntimeError(
            "Transcription could not be completed. Check the API configuration and try again."
        ) from exc

    transcript = getattr(response, "text", "")
    if not isinstance(transcript, str) or not transcript.strip():
        raise ValueError("No speech was detected. Try a clearer or slightly longer recording.")

    cleaned = normalize_report_text(transcript, max_chars=MAX_REPORT_CHARS)
    if not cleaned:
        raise ValueError("No speech was detected. Try a clearer or slightly longer recording.")
    return cleaned
