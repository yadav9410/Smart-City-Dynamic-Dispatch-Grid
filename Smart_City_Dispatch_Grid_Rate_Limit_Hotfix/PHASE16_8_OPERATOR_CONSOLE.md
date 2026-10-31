# Phase 16.8 — Protected Operator Console

## Included

- Separate sidebar route for **Public reporting** and **Operator console**.
- PBKDF2-HMAC-SHA256 password hashing with random salt; no plaintext operator password in source.
- Console locked unless a valid `OPERATOR_PASSWORD_HASH` secret is configured.
- 15-minute inactivity timeout.
- Best-effort five-attempt lockout per Streamlit session.
- Operator-only report listing, report text, consented location, status transitions, and audit history.
- Explicit confirmation before an internal status change.
- Generic error handling for database read and update failures.
- No dispatch, resource reservation, or emergency-service integration.

## Setup

Run from the project folder in a local terminal:

```bash
python -m smartcity.operator_auth
```

Enter a unique password of at least 14 characters twice. Copy the generated `OPERATOR_PASSWORD_HASH = "..."` line to local `.streamlit/secrets.toml` or your deployment secret settings. Do not commit the secrets file. Restart `streamlit run app.py`, choose **Operator console**, and sign in.

The project can be tested with:

```bash
python -m compileall -q app.py smartcity tests
python -m pytest -q
```

## Security caveats

This is prototype-level protection around a shared credential. The login lockout is per Streamlit session, not distributed, and can be bypassed by opening new sessions. It does not provide individual identities or non-repudiable operator attribution. Before handling real emergency or sensitive personal data, replace this approach with a managed identity provider or per-operator accounts, durable shared rate limiting, least-privilege database access, and operational security monitoring.

The operator console's workflow statuses are internal review states, not dispatch states. It must never say that help is on the way. In an immediate emergency in India, call **112** directly.
