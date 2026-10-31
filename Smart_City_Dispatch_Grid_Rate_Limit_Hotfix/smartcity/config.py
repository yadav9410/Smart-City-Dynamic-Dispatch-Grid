"""Central configuration and secret lookup for local and hosted environments."""

from dataclasses import dataclass
import os
from typing import Optional


def get_secret(name: str, default: Optional[str] = None) -> Optional[str]:
    """Read a secret from environment variables, then Streamlit secrets.

    Environment variables take precedence. Do not put API keys directly in code.
    """
    value = os.getenv(name)
    if value:
        return value

    try:
        import streamlit as st

        value = st.secrets.get(name, default)
        return str(value) if value is not None else default
    except Exception:
        # Streamlit secrets are unavailable when importing/testing outside Streamlit.
        return default


def _int_setting(name: str, default: int) -> int:
    raw_value = get_secret(name, str(default))
    try:
        return int(raw_value) if raw_value is not None else default
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    app_name: str = "The Smart City Dynamic Dispatch Grid"
    prototype_mode: bool = True
    emergency_number: str = "112"
    max_report_chars: int = 3000
    database_url: Optional[str] = None
    groq_api_key: Optional[str] = None


settings = Settings(
    app_name=get_secret("APP_NAME", "The Smart City Dynamic Dispatch Grid") or "The Smart City Dynamic Dispatch Grid",
    prototype_mode=True,  # Public prototype must remain simulation-only.
    emergency_number=get_secret("EMERGENCY_NUMBER", "112") or "112",
    max_report_chars=_int_setting("MAX_REPORT_CHARS", 3000),
    database_url=get_secret("DATABASE_URL"),
    groq_api_key=get_secret("GROQ_API_KEY"),
)
