"""Pure helpers for deployment preflight checks; never expose secret values."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

REQUIRED_DEPLOYMENT_FILES = (
    "app.py",
    "requirements.txt",
    ".streamlit/config.toml",
    "smartcity/config.py",
    "smartcity/storage/postgres.py",
    "smartcity/ui/public_intake.py",
    "smartcity/ui/operator_console.py",
    "smartcity/abuse_protection.py",
    "tests",
)


def missing_project_paths(root: str | Path) -> list[str]:
    """Return required app/deployment paths that are missing, relative to root."""
    base = Path(root)
    return [relative for relative in REQUIRED_DEPLOYMENT_FILES if not (base / relative).exists()]


def looks_like_postgres_url(value: str | None) -> bool:
    """Validate the expected URL scheme without echoing credentials or hostnames."""
    return isinstance(value, str) and value.startswith(("postgresql://", "postgres://")) and len(value) > 20


def summarize_secret_presence(
    *, database_url: str | None, operator_password_hash_valid: bool, groq_api_key: str | None
) -> list[tuple[str, str]]:
    """Return safe statuses only, never values for secrets."""
    statuses = [
        ("DATABASE_URL", "configured" if looks_like_postgres_url(database_url) else "MISSING or invalid"),
        (
            "OPERATOR_PASSWORD_HASH",
            "valid format" if operator_password_hash_valid else "MISSING or invalid",
        ),
        ("GROQ_API_KEY", "configured" if bool(groq_api_key and groq_api_key.strip()) else "not configured (voice/AI preview unavailable)"),
    ]
    return statuses
