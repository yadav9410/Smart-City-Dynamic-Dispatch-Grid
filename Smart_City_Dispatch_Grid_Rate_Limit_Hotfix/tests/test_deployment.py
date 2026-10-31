from pathlib import Path

from smartcity.deployment import (
    looks_like_postgres_url,
    missing_project_paths,
    summarize_secret_presence,
)


def test_postgres_url_scheme_is_checked_without_exposing_values():
    assert looks_like_postgres_url("postgresql://u:p@host/db?sslmode=require")
    assert looks_like_postgres_url("postgres://u:p@host/db")
    assert not looks_like_postgres_url(None)
    assert not looks_like_postgres_url("https://user:password@example.com")
    assert not looks_like_postgres_url("postgresql://short")


def test_project_layout_check_passes_for_repository_root():
    root = Path(__file__).resolve().parents[1]
    assert missing_project_paths(root) == []


def test_missing_paths_are_reported_relative_to_root(tmp_path):
    assert "app.py" in missing_project_paths(tmp_path)


def test_secret_statuses_never_include_secret_values():
    url = "postgresql://secret_user:secret_password@secret_host/secret_db"
    key = "gsk_private_example_value"
    result = summarize_secret_presence(
        database_url=url,
        operator_password_hash_valid=True,
        groq_api_key=key,
    )
    rendered = repr(result)
    assert "secret_password" not in rendered
    assert "secret_host" not in rendered
    assert "gsk_private_example_value" not in rendered
    assert ("DATABASE_URL", "configured") in result
    assert ("OPERATOR_PASSWORD_HASH", "valid format") in result
    assert ("GROQ_API_KEY", "configured") in result
