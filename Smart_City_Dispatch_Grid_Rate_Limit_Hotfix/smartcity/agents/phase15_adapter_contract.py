"""Contract and validation helper for connecting exported Phase 1-15 notebook agents.

To use the exact existing intake/triage implementation, create
smartcity/agents/phase15_legacy.py with a function:

    def analyze_public_report(report_text: str) -> dict:
        ...

It should adapt the public report to the Phase 4 CallReport/intake agent, then invoke only
safe intake and triage logic from the existing project. Return a dict matching
PublicIncidentAssessment (see public_pipeline.py). Do not invoke the full dispatch graph,
reserve resources, or read/list other public users' reports in this adapter.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from smartcity.agents.public_pipeline import PublicIncidentAssessment


def validate_phase15_public_result(value: Any) -> dict[str, Any]:
    """Validate and normalize output returned by a custom Phase 1-15 adapter."""
    try:
        parsed = PublicIncidentAssessment.model_validate(value)
    except ValidationError as exc:
        raise ValueError(
            "Phase 1-15 adapter output must match PublicIncidentAssessment fields."
        ) from exc
    parsed.needs_human_review = True
    return parsed.model_dump()
