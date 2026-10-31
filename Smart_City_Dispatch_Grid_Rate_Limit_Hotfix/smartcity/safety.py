"""Public-facing safety language and input helpers."""

PUBLIC_PROTOTYPE_NOTICE = (
    "This is a demonstration only. It does not contact emergency services and does not dispatch real responders."
)
EMERGENCY_INSTRUCTIONS = (
    "If this is an immediate emergency in India, call 112 directly. Do not wait for this prototype."
)


def normalize_report_text(text: str, max_chars: int = 3000) -> str:
    """Normalize and bound a user-supplied text report before processing it."""
    if not isinstance(text, str):
        raise TypeError("Incident report must be text.")
    if max_chars < 1:
        raise ValueError("max_chars must be at least 1.")
    cleaned = " ".join(text.split())
    return cleaned[:max_chars]
