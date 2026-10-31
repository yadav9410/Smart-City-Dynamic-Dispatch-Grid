import importlib
import sys
import types

import pytest

from smartcity.agents.public_pipeline import (
    AgentPipelineConfigurationError,
    AgentPipelineExecutionError,
    PublicIncidentAssessment,
    run_public_agent_pipeline,
)


def sample_assessment():
    return {
        "incident_type": "fire_or_smoke",
        "urgency": "high",
        "confidence": 0.72,
        "summary": "Smoke is reported near an entrance.",
        "hazards": ["smoke"],
        "people_at_risk": "People near the entrance may be exposed.",
        "triage_reason": "Smoke may indicate a fire hazard; human review is required.",
        "needs_human_review": False,
    }


def test_assessment_schema_validates_and_requires_human_review_field():
    value = PublicIncidentAssessment.model_validate(sample_assessment())
    assert value.incident_type == "fire_or_smoke"
    assert value.urgency == "high"


def test_assessment_schema_rejects_invalid_urgency():
    payload = sample_assessment()
    payload["urgency"] = "dispatch_now"
    with pytest.raises(ValueError):
        PublicIncidentAssessment.model_validate(payload)


def test_assessment_schema_rejects_extra_fields():
    payload = sample_assessment()
    payload["resource_id"] = "AMBULANCE-1"
    with pytest.raises(ValueError):
        PublicIncidentAssessment.model_validate(payload)


def test_ai_pipeline_requires_explicit_consent():
    with pytest.raises(ValueError, match="Explicit consent"):
        run_public_agent_pipeline(
            "A test report", consent_to_ai_analysis=False, api_key="secret"
        )


def test_ai_pipeline_requires_api_key():
    with pytest.raises(AgentPipelineConfigurationError, match="GROQ_API_KEY"):
        run_public_agent_pipeline(
            "A test report", consent_to_ai_analysis=True, api_key=None
        )


def test_ai_pipeline_rejects_blank_report():
    with pytest.raises(ValueError, match="report"):
        run_public_agent_pipeline(
            " \n ", consent_to_ai_analysis=True, api_key="secret"
        )


def test_legacy_phase15_adapter_used_if_available(monkeypatch):
    from smartcity.agents import public_pipeline

    fake_module = types.ModuleType("smartcity.agents.phase15_legacy")
    seen = {}

    def analyze_public_report(text):
        seen["text"] = text
        return sample_assessment()

    fake_module.analyze_public_report = analyze_public_report
    monkeypatch.setitem(sys.modules, "smartcity.agents.phase15_legacy", fake_module)
    # Force importlib to use the injected module in this test.
    result = run_public_agent_pipeline(
        "  smoke near entrance  ", consent_to_ai_analysis=True, api_key="key"
    )
    assert seen["text"] == "smoke near entrance"
    assert result["engine"] == "phase1_15_adapter"
    assert result["dispatch_triggered"] is False
    assert result["human_review_required"] is True
    assert result["assessment"]["needs_human_review"] is True


def test_legacy_adapter_invalid_output_is_fail_closed(monkeypatch):
    fake_module = types.ModuleType("smartcity.agents.phase15_legacy")
    fake_module.analyze_public_report = lambda text: {"urgency": "dispatch_now"}
    monkeypatch.setitem(sys.modules, "smartcity.agents.phase15_legacy", fake_module)
    with pytest.raises(AgentPipelineExecutionError, match="unsupported result format"):
        run_public_agent_pipeline(
            "test report", consent_to_ai_analysis=True, api_key="key"
        )


def test_pipeline_does_not_allow_model_result_to_disable_human_review(monkeypatch):
    from smartcity.agents import public_pipeline

    monkeypatch.setattr(
        public_pipeline,
        "_run_groq_compatibility_assessment",
        lambda text, api_key, model: PublicIncidentAssessment.model_validate(sample_assessment()),
    )
    # Force optional legacy module to be absent for this test.
    monkeypatch.delitem(sys.modules, "smartcity.agents.phase15_legacy", raising=False)
    # The test environment has no phase15_legacy module; therefore fallback is used.
    result = run_public_agent_pipeline(
        "a test report", consent_to_ai_analysis=True, api_key="key"
    )
    assert result["assessment"]["needs_human_review"] is True
    assert result["dispatch_triggered"] is False


def test_phase15_contract_validation_normalizes_output():
    from smartcity.agents.phase15_adapter_contract import validate_phase15_public_result

    normalized = validate_phase15_public_result(sample_assessment())
    assert normalized["needs_human_review"] is True
    assert normalized["urgency"] == "high"


def test_compatibility_fallback_uses_structured_schema(monkeypatch):
    import smartcity.agents.public_pipeline as pipeline

    monkeypatch.setattr(
        pipeline,
        "_run_groq_compatibility_assessment",
        lambda report_text, api_key, model: PublicIncidentAssessment.model_validate(sample_assessment()),
    )
    # Make sure no legacy adapter will be loaded.
    monkeypatch.setattr(pipeline, "_load_legacy_adapter", lambda: None)
    result = pipeline.run_public_agent_pipeline(
        "fictional report", consent_to_ai_analysis=True, api_key="test-key"
    )
    assert result["engine"] == "groq_structured_compatibility_assessment"
    assert result["assessment"]["needs_human_review"] is True
    assert result["dispatch_triggered"] is False
