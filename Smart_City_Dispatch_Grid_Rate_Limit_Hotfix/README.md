# The Smart City Dynamic Dispatch Grid

A public-facing prototype for AI-assisted incident intake, correlation, triage, and **simulated** resource planning.

## Important safety boundary

This is a demonstration only. It does not contact emergency services or dispatch real responders. If there is an immediate emergency in India, call **112** directly. Do not wait for this prototype. A recorded request must never be represented as a confirmed dispatch.

## Phase 16.1 status

This phase creates the project structure, configuration helpers, safety copy, and initial Streamlit landing page. It does not yet collect reports, record audio, request GPS, connect to a database, or run the agent workflow. Those capabilities are added in later phases.

## Project layout

```text
smart_city_dispatch_grid/
├── app.py
├── requirements.txt
├── README.md
├── .gitignore
├── .streamlit/
│   └── config.toml
├── smartcity/
│   ├── config.py
│   ├── safety.py
│   ├── agents/
│   ├── storage/
│   └── ui/
└── tests/
    └── test_safety.py
```

## Run locally

Use Python 3.11 or 3.12 in a virtual environment.

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
streamlit run app.py
```

## Secrets

Use environment variables or Streamlit secrets. Never commit `.streamlit/secrets.toml`, `.env`, or API keys to GitHub.

Expected names for later phases:

- `GROQ_API_KEY`
- `DATABASE_URL`
- `MAX_REPORT_CHARS` (optional; defaults to 3000)
- `EMERGENCY_NUMBER` (optional; defaults to 112)

For Streamlit Community Cloud, configure secrets in the app's settings. See the official Streamlit documentation: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management

## Existing Colab work

Do not delete or overwrite the completed Phase 1–15 notebook. The existing schemas, agent functions, workflow, and evaluation code will be migrated into this package incrementally. Local SQLite state from Colab will not automatically persist in a deployed app; the public deployment will use a hosted database in a later phase.

## Phase 16.2 — PostgreSQL persistence

The storage layer lives in `smartcity/storage/postgres.py`. It creates two tables:

- `public_incident_reports`: user-submitted report text, consented location fields, timestamps, and internal review status.
- `public_audit_events`: minimal event metadata without report text or raw audio.

### Configure PostgreSQL

Create a PostgreSQL database with a trusted provider (for example, Neon). Copy its PostgreSQL connection URL from the provider's connection dialog. Keep the provider's TLS/SSL parameters such as `sslmode=require` in the URL.

For Colab, add a secret named `DATABASE_URL` in **Secrets** (key icon) and grant the notebook access. Do not paste a real connection URL in a notebook cell, source file, chat, or Git commit. For local development, place it in `.streamlit/secrets.toml`, which is ignored by Git. For deployment, configure the secret in the hosting platform's settings.

### Initialize the schema

Run the following from the project directory after configuring `DATABASE_URL`:

```python
from smartcity.storage.postgres import initialize_database
initialize_database()
print("Phase 16.2 database schema initialized.")
```

`initialize_database()` is idempotent and creates tables/indexes only; it does not import or delete data from the old Colab SQLite database. Run it explicitly against the intended database. The app landing page does not connect to the database automatically in Phase 16.2.

### Storage and access boundaries

- The `create_public_report()` function requires `consent_to_store_report=True`; the future UI must collect this explicit opt-in before calling it. Location consent is separate.
- Location is stored only when `consent_to_store_location=True`; GPS latitude and longitude must be a valid pair.
- Store only a reviewed transcript for voice submissions, never raw audio.
- `get_public_report()` and `list_public_reports()` return report content and are operator-only helpers. The app calls list/detail readers only inside the authenticated operator-console view; keep them out of public-facing code paths.
- Public receipt output is limited to the reference code, recorded status, and timestamp. It is not a dispatch confirmation.
- Database rows can include sensitive incident information. Restrict database credentials and configure retention/deletion policies before inviting the public.


## Phase 16.3 — Public text-only incident intake

The public landing page now contains a text submission form. It requires two separate acknowledgements: consent to store the report and confirmation that the app is only a prototype. The UI calls `create_public_report()` only after both are checked. It does not collect location, audio, or contact details in this phase.

### Start the app

From this project directory, after setting `DATABASE_URL` and initializing the Phase 16.2 schema:

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

If a PostgreSQL URL is not configured, submission stays disabled. If the database is configured but the schema is missing or the database is unavailable, the UI reports a generic storage error and never displays driver/database exception details. A successful receipt displays only the reference code, internal `recorded` status, and timestamp. This is not a dispatch confirmation.

### Phase boundary

This is not yet ready for broad public promotion. Rate limiting, abuse controls, access-controlled operator review, retention/deletion policy, and deployment hardening remain future phases. Voice input, GPS, and map views are implemented in later phases. The UI must never claim that emergency services have been notified. In an immediate emergency in India, call 112 directly.


## Phase 16.4 — Location input and interactive map

The public form supports optional browser geolocation, a clickable Folium/OpenStreetMap pin, manually entered latitude/longitude, and an optional address/landmark label. The map starts at a generic center in India and does not assume the visitor's location.

Location sharing has separate consent from report-text storage. Coordinates and labels are omitted from the database unless the location-consent checkbox is checked. Browser GPS requires a supported browser and a secure context (HTTPS or localhost); if unavailable or denied, users can click the map or enter coordinates. Address labels are not geocoded or sent to a geocoding provider.

No location selection calls emergency services or initiates real dispatch. The initial map center and map tiles are supplied by OpenStreetMap. Map tile requests can reveal the geographic area being viewed, along with normal network metadata, to the tile provider.


## Phase 16.5 — Voice recording and speech-to-text

The public intake page now optionally lets a user record a short voice description with Streamlit's audio-input widget. When the user checks the **separate voice-transcription consent** and clicks **Transcribe recording**, the app sends the captured audio to the configured Groq speech-to-text API using `whisper-large-v3-turbo` by default. The model supports multilingual transcription; the UI offers auto-detect, English, Hindi, Punjabi, and Urdu. See the current provider documentation for model and request limits: https://console.groq.com/docs/speech-to-text and Streamlit's audio recording widget docs: https://docs.streamlit.io/develop/api-reference/widgets/st.audio_input.

After recording, the page immediately displays an editable **Transcript (editable)** box. Recording alone cannot reveal the spoken words: users must check transcription consent and click **Convert recording to text**; once Groq finishes, the recognized words populate that box. If the Groq key is not configured, the box remains available for manual typing and the page explains that automatic speech-to-text is unavailable. Users must review the text, optionally copy it into the report description, and then separately consent to storing the report and acknowledge that the app is only a prototype. The database records only the reviewed text and marks `input_method` as `voice_transcription`; the raw recording is not saved by the app to disk or PostgreSQL. Audio bytes remain transiently available in the Streamlit session while the user is working and are sent to Groq only after the explicit Transcribe button click. Consider the transcription provider's current data-handling terms before using the public app with real reports.

Configure `GROQ_API_KEY` using Colab Secrets, local `.streamlit/secrets.toml`, environment variables, or the deployment secret manager. Never hardcode the key. Voice recordings are capped at 8 MiB in this app, the app uses a 30-second client timeout and one retry, and errors shown to users do not include raw SDK messages. The UI does not initiate emergency calls or dispatch real responders; for an immediate emergency in India, call 112 directly.

## Phase 16.6 — Agent integration

This phase adds a consent-gated, button-triggered AI assessment preview after report storage.
The preview uses an optional exported adapter at `smartcity/agents/phase15_legacy.py`; when that
module isn't available, it uses a constrained Groq structured-output compatibility assessment.
The fallback is not claimed to be the original notebook graph. AI results remain in session state
and are not persisted to PostgreSQL. The public flow never invokes the full dispatch graph or
creates/reserves assignments. See `PHASE16_6_AGENT_INTEGRATION.md` for the adapter contract.

## Phase 16.7 — Simulated resources, routes, and map layers

The optional map preview in `smartcity/ui/simulation_map.py` draws synthetic medical, fire/rescue, rescue, and safety-support markers plus dashed straight-line illustrations. All unit identifiers start with `SIM-`; they are deterministic placeholders, not real stations, vehicles, or real availability. The map has separate layer controls for the fictional scenario point, synthetic resources, and simulated route lines.

By default, the simulation uses a generic demonstration center in India, not the visitor's location. To use a currently selected map pin, the visitor must explicitly enable the separate **Use my currently selected map pin for this simulation only** control. A new pin resets that control. Simulation coordinates are generated locally and are not sent to a route or geocoding provider. OpenStreetMap tile requests occur only when the map is shown and may reveal the map area being viewed to the tile provider.

The dashed lines are straight-line illustrations based on great-circle distance, not road routes or driving directions. There is no live unit feed, location tracking, resource matching, assignment, reservation, dispatch, or ETA. This phase is strictly a visualization; no assignment function from the Phase 1–15 workflow is called. The public UI labels all mock layers as simulated and makes the map opt-in.

### Phase 16.7 validation

From the project root:

```bash
python -m compileall -q app.py smartcity tests
python -m pytest -q
```

This phase's pure-Python tests verify deterministic mock units, coordinate bounds, distance calculation, and explicit simulation-only output flags. Separately test the interactive Folium layer controls in a browser before deploying.


## Phase 16.8 — Protected operator console

The app now has a separate **Operator console** view. Report listing, report text, consented location, and audit-event readers are called only inside that view after password-hash authentication. The console supports review of stored reports and only exposes status transitions allowed by the storage layer. Every status change requires an explicit confirmation that it is an internal workflow action, not dispatch.

### Configure operator access

1. From the project directory, run `python -m smartcity.operator_auth` in a local terminal. Enter a unique password of at least 14 characters when prompted. The input is not echoed.
2. Copy the generated `OPERATOR_PASSWORD_HASH = "..."` line into your local `.streamlit/secrets.toml`, or add `OPERATOR_PASSWORD_HASH` to the deployment platform's secrets. Do **not** put the plaintext password in the project or commit the hash/secrets file.
3. Restart the app and select **Operator console** from the sidebar. If no valid hash is configured, the console stays locked.

The password is hashed using PBKDF2-HMAC-SHA256 with a random salt. The console's inactivity timeout is 15 minutes. It also implements a best-effort login lockout after five failed attempts per Streamlit session.

### Security limitations

This phase provides prototype-level access protection, not production-grade identity management. It uses one shared operator credential; login throttling is per session and can be bypassed by creating new sessions. Before handling real emergency reports or sensitive personal data, use a managed identity provider or individual accounts, durable rate limiting, least-privilege database credentials, audit review, retention/deletion controls, and deployment hardening. Do not make the console public until these protections are appropriate for the data being processed.

### Operator workflow

- Filter reports by internal status and choose a report for review.
- View the stored report text and location only when the reporter consented to store location.
- Change status only through allowed transitions from `VALID_STATUSES` / `ALLOWED_STATUS_TRANSITIONS`.
- Review the minimal audit history for the selected reference.

No `dispatched` status exists in this storage contract. This console does not call dispatch reservation functions, contact public-safety services, or tell the public that help is on the way. For an immediate emergency in India, call **112** directly.


## Phase 16.9 — Privacy, reliability, and abuse protection

Phase 16.9 adds rolling session quotas of 3 report submissions, 3 transcription calls, and 4 AI previews per 10 minutes, with an atomic PostgreSQL-backed counter keyed by a SHA-256 digest of a random server-generated session token. The database only stores the token hash, action name, counter, and timestamps; inactive limiter records are opportunistically removed after 24 hours. The application fails closed when a configured PostgreSQL limiter cannot be checked.

The application caps reports at 3,000 characters, voice recordings at 8 MiB, Streamlit WebSocket messages at 12 MiB, and configures database connection/statement timeouts. Streamlit usage-stat collection is disabled, browser-visible exception details are hidden, and safe static operational log markers do not include report text, location, audio, API keys, or database exceptions. Pending AI-preview text is cleared from session state after 15 minutes if not used.

**Rate-limit limitation:** this is session-level throttling, not IP/account-wide protection. A visitor can create a new Streamlit session, and the app does not treat client-supplied forwarding headers as trusted identity. Before broad public release, use trusted hosting/proxy/WAF limits, individual operator accounts or a managed identity provider, least-privilege DB access, monitoring, and tested retention/deletion procedures. The project does not yet automatically delete stored reports; the public page discloses this and discourages submission of real sensitive incident information.

After updating the code, run `initialize_database()` again against the intended PostgreSQL database so the new `public_request_limits` table and its index are created. This initializer is idempotent. See `PHASE16_9_ABUSE_PROTECTION.md` for the deployment checklist and limits.

## Phase 16.10 — Deployment and launch preparation

See [`DEPLOYMENT.md`](DEPLOYMENT.md) for the end-to-end deployment procedure, safe GitHub preparation, Streamlit Community Cloud setup, secrets handling, schema verification, smoke testing, rollback, and operational cautions.

This phase adds `.github/workflows/ci.yml` to run compilation and tests on Python 3.12 for pushes and pull requests, plus `scripts/deployment_preflight.py` to check the project layout and secret readiness without printing secret values. Use `--check-db` only when you want a read-only connection and table-existence check. The preflight does not automatically initialize or modify the database.

**Deployment status:** packaging and CI checks do not mean the app has been deployed. Phase 16.10 is complete only after you push the repository, pass the workflow, configure secrets in Streamlit Community Cloud, confirm the database schema, deploy, and complete the manual smoke test. Keep the prototype restricted to fictional/test data until privacy, authentication, rate-limiting, and retention requirements are appropriate for your real use case.


### If the app says DATABASE_URL or GROQ_API_KEY is missing

These are runtime secrets, not Python packages. On Streamlit Community Cloud, open **Manage app → Settings → Secrets**, add `DATABASE_URL`, `GROQ_API_KEY`, and `OPERATOR_PASSWORD_HASH` using valid TOML syntax, then save and allow the app to restart. If a secret has been exposed, rotate it first. Never put real secrets in this repository. See `DEPLOYMENT.md` for the secret template.

## Public reporting flow

The public page is organized in this order: emergency guidance, incident description,
optional voice recording and transcript review, required location selection, consent
confirmation, and report submission. A location can be supplied by browser GPS, a map
pin, manual coordinates, or an address/landmark. The location is stored only when the
visitor separately consents to location storage. Prototype-boundary and privacy details
are placed at the bottom of the public page. This remains a simulation-only prototype;
it does not contact emergency services or dispatch responders.

## Phase 16.9 rate-limit hotfix (2026-10-31)

If transcription or another protected action displays `The request-protection check is temporarily unavailable`, the app's database-backed rate limiter could not complete. The most common deployment cause is that `public_request_limits` was not created in the same Neon database/branch used by Streamlit after the Phase 16.9 update.

Open the Neon SQL Editor for the database/branch in Streamlit's `DATABASE_URL`, run `scripts/initialize_phase16_9_rate_limit.sql`, and verify that the final query returns `public.public_request_limits`. Then restart the Streamlit app and retry once. See `PHASE16_9_RATE_LIMIT_TROUBLESHOOTING.md` for other possible causes.
