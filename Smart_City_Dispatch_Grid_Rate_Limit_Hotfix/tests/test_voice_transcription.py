import sys
import types

import pytest

from smartcity.ui.voice_transcription import (
    DEFAULT_TRANSCRIPTION_MODEL,
    MAX_AUDIO_BYTES,
    prepare_audio_payload,
    transcribe_audio_bytes,
)


def test_prepare_audio_payload_accepts_browser_wav():
    filename, payload, mime_type = prepare_audio_payload(b"audio-bytes", "audio/wav")
    assert filename == "voice_report.wav"
    assert payload == b"audio-bytes"
    assert mime_type == "audio/wav"


def test_prepare_audio_payload_normalizes_mime_parameters():
    filename, _, mime_type = prepare_audio_payload(b"data", "audio/webm;codecs=opus")
    assert filename == "voice_report.webm"
    assert mime_type == "audio/webm"


def test_prepare_audio_payload_defaults_missing_type_to_wav():
    filename, _, mime_type = prepare_audio_payload(b"data", None)
    assert filename == "voice_report.wav"
    assert mime_type == "audio/wav"


def test_prepare_audio_payload_rejects_empty_audio():
    with pytest.raises(ValueError, match="Record a short voice report"):
        prepare_audio_payload(b"", "audio/wav")


def test_prepare_audio_payload_rejects_unsupported_type():
    with pytest.raises(ValueError, match="format is not supported"):
        prepare_audio_payload(b"data", "application/pdf")


def test_prepare_audio_payload_rejects_oversized_audio():
    with pytest.raises(ValueError, match="too large"):
        prepare_audio_payload(b"data", "audio/wav", max_bytes=1)


def test_transcription_requires_explicit_consent_before_sending_audio():
    with pytest.raises(ValueError, match="Explicit consent"):
        transcribe_audio_bytes(b"data", "audio/wav", consent_to_transcribe=False, api_key="test-key")


def test_transcription_requires_api_key_before_loading_sdk():
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        transcribe_audio_bytes(
            b"data", "audio/wav", consent_to_transcribe=True, api_key=None
        )


def test_transcription_calls_groq_and_returns_normalized_text(monkeypatch):
    captured = {}

    class FakeTranscriptions:
        def create(self, **kwargs):
            captured["request"] = kwargs
            return types.SimpleNamespace(text="  Smoke\n is visible near the gate.  ")

    class FakeClient:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.audio = types.SimpleNamespace(transcriptions=FakeTranscriptions())

    monkeypatch.setitem(sys.modules, "groq", types.SimpleNamespace(Groq=FakeClient))
    result = transcribe_audio_bytes(
        b"audio-bytes",
        "audio/wav",
        consent_to_transcribe=True,
        api_key="test-key",
        language="hi",
    )

    assert result == "Smoke is visible near the gate."
    assert captured["client"]["api_key"] == "test-key"
    request = captured["request"]
    assert request["model"] == DEFAULT_TRANSCRIPTION_MODEL
    assert request["language"] == "hi"
    assert request["file"] == ("voice_report.wav", b"audio-bytes", "audio/wav")
    assert request["temperature"] == 0.0


def test_transcription_omits_language_for_auto_detect(monkeypatch):
    captured = {}

    class FakeTranscriptions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return types.SimpleNamespace(text="Short fictional report")

    class FakeClient:
        def __init__(self, **kwargs):
            self.audio = types.SimpleNamespace(transcriptions=FakeTranscriptions())

    monkeypatch.setitem(sys.modules, "groq", types.SimpleNamespace(Groq=FakeClient))
    result = transcribe_audio_bytes(
        b"audio-bytes", "audio/wav", consent_to_transcribe=True, api_key="test-key", language=None
    )
    assert result == "Short fictional report"
    assert "language" not in captured


def test_transcription_rejects_unsupported_model():
    with pytest.raises(ValueError, match="Unsupported transcription model"):
        transcribe_audio_bytes(
            b"data", "audio/wav", consent_to_transcribe=True, api_key="test-key", model="unknown-model"
        )


def test_transcription_returns_safe_error_for_sdk_failure(monkeypatch):
    class FakeTranscriptions:
        def create(self, **kwargs):
            raise RuntimeError("PRIVATE SDK DETAIL SHOULD NOT BE SHOWN")

    class FakeClient:
        def __init__(self, **kwargs):
            self.audio = types.SimpleNamespace(transcriptions=FakeTranscriptions())

    monkeypatch.setitem(sys.modules, "groq", types.SimpleNamespace(Groq=FakeClient))
    with pytest.raises(RuntimeError, match="Transcription could not be completed") as exc_info:
        transcribe_audio_bytes(b"data", "audio/wav", consent_to_transcribe=True, api_key="test-key")
    assert "PRIVATE SDK DETAIL" not in str(exc_info.value)


def test_transcription_rejects_empty_transcript(monkeypatch):
    class FakeTranscriptions:
        def create(self, **kwargs):
            return types.SimpleNamespace(text="   ")

    class FakeClient:
        def __init__(self, **kwargs):
            self.audio = types.SimpleNamespace(transcriptions=FakeTranscriptions())

    monkeypatch.setitem(sys.modules, "groq", types.SimpleNamespace(Groq=FakeClient))
    with pytest.raises(ValueError, match="No speech was detected"):
        transcribe_audio_bytes(b"data", "audio/wav", consent_to_transcribe=True, api_key="test-key")


def test_audio_limit_is_below_25mb():
    assert MAX_AUDIO_BYTES < 25 * 1024 * 1024
