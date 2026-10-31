# Phase 16.9 — Privacy, Reliability, and Abuse Protection

This phase adds prototype-scale safeguards around public report submission, audio transcription, and optional AI assessment. It does not convert the project into a production emergency-response system.

## Controls added

- **Rolling action limits per Streamlit session:** up to 3 report submissions, 3 voice-transcription calls, and 4 AI previews per 10-minute window.
- **Database-backed session limits:** when `DATABASE_URL` is configured, an atomic PostgreSQL upsert tracks the allow-listed action by a SHA-256 digest of a random server-generated session token. Only the hash, action code, counters, and timestamps are stored; report text, location, raw audio, API keys, and IP addresses are not part of this table.
- **Fail-closed behavior for the configured limiter:** if `DATABASE_URL` is set but the rate-limit table/query cannot be used, report submission and external API calls are blocked with a generic message rather than bypassing the configured protection.
- **Bounded resource usage:** report text remains limited to 3,000 characters; voice audio is capped at 8 MiB; Streamlit upload/message sizes are bounded; database connection and statement timeouts are set; Groq calls use explicit timeouts and limited retries.
- **Safe failure messages:** public UI errors avoid exposing SQL, database connection details, request payloads, raw audio, or provider exception text. Static operational log markers do not include report content.
- **Privacy disclosure:** the public page warns that no automatic report-retention schedule is enforced yet and that the app is a prototype.
- **Streamlit privacy configuration:** usage-stat collection is disabled, detailed exceptions are hidden from the app UI, and the audio upload cap matches the application-level bound.

## Upgrade steps

1. Extract this project's ZIP over the existing `/content/smart_city_dispatch_grid` directory in Colab, or replace the local project files.
2. Install/update dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

3. Run the test suite:

   ```bash
   python -m compileall -q app.py smartcity tests
   python -m pytest -q
   ```

4. **Re-run `initialize_database()` against the intended PostgreSQL database.** It is idempotent and now also creates `public_request_limits` and its cleanup index. Do not run a schema initializer with an untrusted database URL.
5. Keep `DATABASE_URL`, `GROQ_API_KEY`, and `OPERATOR_PASSWORD_HASH` in Colab Secrets, environment variables, `.streamlit/secrets.toml` (local only), or deployment secrets. Never commit real secrets.
6. Run `streamlit run app.py` locally and verify the intake, transcript, AI preview, and operator-login paths using fictional reports.

## Rate-limit semantics and limits

The quotas are keyed to a server-generated random token held in Streamlit session state. The database stores its SHA-256 digest. They reduce repeated actions in the same server-side session and retain a counter across app reruns while that token remains alive. A user can create a fresh session, and Streamlit does not expose a reliable client IP to this application by default. Therefore **these limits are not IP-wide, identity-wide, or sufficient for denial-of-service protection**. The opportunistic database cleanup removes inactive limiter records older than 24 hours; it is not a report-retention mechanism.

Before broad public promotion, configure request limits at the hosting/proxy/WAF layer and verify they operate on the correct client identity. Add individual operator identities or a managed identity provider, least-privilege PostgreSQL credentials, backup/retention/deletion procedures, monitoring/alerts, and a tested incident-response plan. Do not trust a client-supplied `X-Forwarded-For` header as an identity unless a trusted proxy overwrites it.

## Data retention and privacy

This phase does not automatically delete stored incident reports. Database administrators must define the report-retention period and deletion procedure appropriate for their test data and applicable requirements before real public use. Location fields are still stored only with separate location-storage consent, and raw audio is not persisted by the app. When a user explicitly consents and clicks the transcription button, audio is sent to the configured Groq transcription API; an optional AI preview sends only report text, not location, to the configured model.

The rate-limit table contains pseudonymous session-token hashes, action names, counters, and timestamps; expired rows are opportunistically cleaned after 24 hours. Do not treat this as anonymization of the incident reports themselves.

## Emergency safety boundary

The public prototype continues to store reports and optionally display AI assessment previews. It does not contact emergency services, assign or reserve real responders, or claim help is on the way. For an immediate emergency in India, call **112** directly.
