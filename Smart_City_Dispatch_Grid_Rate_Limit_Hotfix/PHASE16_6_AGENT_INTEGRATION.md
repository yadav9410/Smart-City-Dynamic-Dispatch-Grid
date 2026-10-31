# Phase 16.6 — Public Agent Integration

## Safety boundary

The public UI runs a consent-gated, non-binding assessment after the report is stored and the
user clicks **Run AI assessment preview**. It does not call the complete `dispatch_workflow`,
does not create/reserve assignments, and does not read other users' reports. Cross-report
correlation remains an operator-only activity until access control and privacy review exist.

## How this package works

1. The app requires a distinct consent to send the report text to the configured AI model.
2. On explicit button click, it first looks for `smartcity.agents.phase15_legacy.analyze_public_report(report_text)`.
3. If that exact Phase 1-15 adapter module has not been exported, a structured-output Groq
   compatibility assessment is used. The UI must label this honestly as a compatibility assessment,
   not the original Phase 1-15 graph.
4. AI output is held in Streamlit session state only and is not stored in PostgreSQL by this phase.
5. Human review remains mandatory regardless of the model's output.

## Connecting the original notebook agents

Notebook functions that only exist in a running Colab notebook are not importable by the deployed
Streamlit app. Export the relevant Phase 4 intake function plus safe Phase 8 triage logic to a
Python module named `smartcity/agents/phase15_legacy.py`. Define:

```python
def analyze_public_report(report_text: str) -> dict:
    # Adapt report_text to the existing CallReport/intake schema.
    # Call the existing intake and triage code; do not invoke the full dispatch graph.
    # Normalize the result to the fields below and return a dict.
    return {
        "incident_type": "unclear",
        "urgency": "uncertain",
        "confidence": 0.0,
        "summary": "Assessment could not determine enough detail.",
        "hazards": [],
        "people_at_risk": "unclear from report",
        "triage_reason": "Insufficient information; human review is required.",
        "needs_human_review": True,
    }
```

The example is a schema example, not an actual assessment algorithm. Do not return a hard-coded
result in production. The accepted values and lengths are enforced by `PublicIncidentAssessment`
in `smartcity/agents/public_pipeline.py`.

For the exact previous notebook implementation, adapt against the real schemas and function
signatures from the notebook; don't guess those signatures. Do not pass coordinates to the AI
adapter in this public phase, and do not correlate against stored reports from other people.

## Environment

- `GROQ_API_KEY`: required for the built-in compatibility assessment.
- `AGENT_MODEL`: optional, defaults to `openai/gpt-oss-120b`.
- Keep all credentials in environment variables or deployment secrets.

## Current limits

The model output is fallible and must not be used for emergency decisions. This phase doesn't
contact emergency services or dispatch responders. In India, call 112 for immediate emergencies.
