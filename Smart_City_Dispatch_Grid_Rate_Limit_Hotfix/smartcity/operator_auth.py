"""Password-hash authentication helpers for the prototype operator console.

This module provides a single shared operator credential for a small prototype.
It is not a replacement for an identity provider or server-side distributed rate
limiting in a production system handling real emergency or personal data.
"""

from __future__ import annotations

import base64
import binascii
import getpass
import hashlib
import hmac
import secrets
import time
from typing import MutableMapping, Optional

from smartcity.config import get_secret

HASH_SCHEME = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 310_000
MIN_ITERATIONS = 200_000
MAX_ITERATIONS = 600_000
SALT_BYTES = 16
KEY_BYTES = 32
MIN_PASSWORD_LENGTH = 14
MAX_PASSWORD_LENGTH = 1024
OPERATOR_SESSION_TTL_SECONDS = 15 * 60
MAX_LOGIN_ATTEMPTS_PER_SESSION = 5
LOGIN_LOCKOUT_SECONDS = 5 * 60

_OPERATOR_SESSION_KEYS = (
    "operator_authenticated",
    "operator_last_activity",
    "operator_session_expired",
)


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_operator_password(password: str, *, iterations: int = DEFAULT_ITERATIONS) -> str:
    """Create a portable PBKDF2-SHA256 password hash for deployment secrets."""
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Operator password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"Operator password must be at most {MAX_PASSWORD_LENGTH} characters.")
    if not MIN_ITERATIONS <= iterations <= MAX_ITERATIONS:
        raise ValueError(f"iterations must be between {MIN_ITERATIONS} and {MAX_ITERATIONS}.")
    salt = secrets.token_bytes(SALT_BYTES)
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations, dklen=KEY_BYTES
    )
    return f"{HASH_SCHEME}${iterations}${_b64encode(salt)}${_b64encode(derived)}"


def _parse_password_hash(encoded_hash: str) -> Optional[tuple[int, bytes, bytes]]:
    if not isinstance(encoded_hash, str):
        return None
    parts = encoded_hash.split("$")
    if len(parts) != 4 or parts[0] != HASH_SCHEME:
        return None
    try:
        iterations = int(parts[1])
        salt = _b64decode(parts[2])
        digest = _b64decode(parts[3])
    except (ValueError, TypeError, binascii.Error):
        return None
    if not MIN_ITERATIONS <= iterations <= MAX_ITERATIONS:
        return None
    if len(salt) < SALT_BYTES or len(digest) != KEY_BYTES:
        return None
    return iterations, salt, digest


def get_operator_password_hash() -> Optional[str]:
    """Load OPERATOR_PASSWORD_HASH from environment or Streamlit secrets."""
    value = get_secret("OPERATOR_PASSWORD_HASH")
    return value.strip() if isinstance(value, str) and value.strip() else None


def is_operator_auth_configured() -> bool:
    """Return true only when a syntactically valid password hash is configured."""
    encoded_hash = get_operator_password_hash()
    return bool(encoded_hash and _parse_password_hash(encoded_hash))


def verify_operator_password(password: str, encoded_hash: Optional[str] = None) -> bool:
    """Constant-time verify a password against a configured or supplied hash."""
    if not isinstance(password, str) or len(password) > MAX_PASSWORD_LENGTH:
        return False
    if encoded_hash is None:
        encoded_hash = get_operator_password_hash()
    parsed = _parse_password_hash(encoded_hash or "")
    if parsed is None:
        return False
    iterations, salt, expected = parsed
    actual = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations, dklen=KEY_BYTES
    )
    return hmac.compare_digest(actual, expected)


def clear_operator_session(state: MutableMapping[str, object], *, expired: bool = False) -> None:
    """Clear authentication state without disturbing public intake form data."""
    for key in _OPERATOR_SESSION_KEYS:
        state.pop(key, None)
    if expired:
        state["operator_session_expired"] = True


def maintain_operator_session(
    state: MutableMapping[str, object], *, now: Optional[float] = None
) -> bool:
    """Enforce inactivity timeout and refresh activity on each app rerun.

    Returns whether the operator session remains authenticated. Streamlit reruns
    caused by page activity refresh the 15-minute inactivity timer.
    """
    if state.get("operator_authenticated") is not True:
        return False
    current = time.time() if now is None else float(now)
    last_activity = state.get("operator_last_activity")
    if not isinstance(last_activity, (int, float)) or current - float(last_activity) > OPERATOR_SESSION_TTL_SECONDS:
        clear_operator_session(state, expired=True)
        return False
    state["operator_last_activity"] = current
    return True


def main() -> None:
    """Interactive helper: generate a hash without echoing the password."""
    password = getpass.getpass("Create operator password (14+ characters): ")
    confirmation = getpass.getpass("Confirm operator password: ")
    if password != confirmation:
        raise SystemExit("Passwords did not match; no hash was generated.")
    try:
        encoded_hash = hash_operator_password(password)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print("\nAdd this line to your local .streamlit/secrets.toml or deployment secrets:\n")
    print(f'OPERATOR_PASSWORD_HASH = "{encoded_hash}"')
    print("\nKeep the hash private and never commit secrets.toml to source control.")


if __name__ == "__main__":
    main()
