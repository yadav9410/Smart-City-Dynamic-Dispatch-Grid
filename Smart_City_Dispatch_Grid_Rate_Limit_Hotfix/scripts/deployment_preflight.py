#!/usr/bin/env python3
"""Check deployment files and configuration without printing secret values.

Usage:
  python scripts/deployment_preflight.py --static-only
  python scripts/deployment_preflight.py
  python scripts/deployment_preflight.py --check-db

The default checks required secrets. --check-db additionally makes a read-only
connection and verifies that the required PostgreSQL tables exist; it never runs
schema initialization or changes database contents.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from smartcity.config import get_secret  # noqa: E402
from smartcity.deployment import missing_project_paths, summarize_secret_presence  # noqa: E402
from smartcity.operator_auth import is_operator_auth_configured  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--static-only",
        action="store_true",
        help="check project files only; useful for CI without deployment secrets",
    )
    parser.add_argument(
        "--check-db",
        action="store_true",
        help="verify connectivity and required table presence with read-only queries",
    )
    args = parser.parse_args()

    print("Smart City Dispatch Grid — deployment preflight")
    missing = missing_project_paths(ROOT)
    if missing:
        for item in missing:
            print(f"FAIL  required project path missing: {item}")
    else:
        print("PASS  required project files are present")

    if not args.static_only:
        statuses = summarize_secret_presence(
            database_url=get_secret("DATABASE_URL"),
            operator_password_hash_valid=is_operator_auth_configured(),
            groq_api_key=get_secret("GROQ_API_KEY"),
        )
        for name, status in statuses:
            if name == "GROQ_API_KEY" and status.startswith("not configured"):
                print(f"WARN  {name}: {status}")
            elif status in {"configured", "valid format"}:
                print(f"PASS  {name}: {status}")
            else:
                print(f"FAIL  {name}: {status}")

    db_failed = False
    if args.check_db:
        try:
            from smartcity.storage.postgres import _connect

            required_tables = (
                "public.public_incident_reports",
                "public.public_audit_events",
                "public.public_request_limits",
            )
            with _connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT to_regclass(%s) AS table_name",
                        (required_tables[0],),
                    )
                    for table_name in required_tables:
                        cursor.execute("SELECT to_regclass(%s) AS table_name", (table_name,))
                        row = cursor.fetchone()
                        if not row or not row.get("table_name"):
                            print(f"FAIL  required database table missing: {table_name}")
                            db_failed = True
            if not db_failed:
                print("PASS  PostgreSQL connection and required tables verified")
        except Exception:
            # Deliberately don't expose exception text, URLs, hostnames, or SQL details.
            print("FAIL  PostgreSQL check failed; verify DATABASE_URL, network access, permissions, and schema")
            db_failed = True

    secret_failed = False
    if not args.static_only:
        secret_failed = any(
            status in {"MISSING or invalid"}
            for _, status in summarize_secret_presence(
                database_url=get_secret("DATABASE_URL"),
                operator_password_hash_valid=is_operator_auth_configured(),
                groq_api_key=get_secret("GROQ_API_KEY"),
            )
        )
    failed = bool(missing) or secret_failed or db_failed
    if failed:
        print("\nPreflight result: NOT READY. Fix the FAIL checks before deployment.")
        return 1
    print("\nPreflight result: checks passed. This does not replace browser/manual security testing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
