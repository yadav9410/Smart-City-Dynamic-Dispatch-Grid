# Phase 16.9 rate-limit troubleshooting

If the UI says `The request-protection check is temporarily unavailable`, the
app is configured with a PostgreSQL URL but the database-backed limiter could
not complete its check. Common causes are:

1. `public.public_request_limits` was not created after the Phase 16.9 update.
2. Streamlit's `DATABASE_URL` points to a different Neon project or branch than
the one where the schema was initialized.
3. The configured database role cannot connect or does not have INSERT/UPDATE/
DELETE permissions on the rate-limit table.
4. The database is temporarily unavailable or the connection URL is invalid.

## Recommended repair

1. Open the Neon project and branch that match Streamlit's `DATABASE_URL`.
2. Open **SQL Editor**.
3. Run `scripts/initialize_phase16_9_rate_limit.sql` from this project. The SQL
   is idempotent and only creates the rate-limit table/index if absent.
4. Confirm the query result is `public.public_request_limits`.
5. Restart the Streamlit app and retry transcription once.

If the table already exists and the error remains, open Streamlit **Manage app →
Logs** and look for a safe log entry beginning with
`persistent_rate_limit_check_failed`. The app logs only the exception class and
PostgreSQL SQLSTATE, never the connection URL or exception text. Examples:

- `UndefinedTable` / `42P01`: required table is missing from the DB/branch.
- `InsufficientPrivilege` / `42501`: database role lacks required table rights.
- Connection/timeout exception with no SQLSTATE: verify URL, branch, network,
and database availability.

Do not disable the fail-closed limiter to make the button work. Do not paste
connection URLs, passwords, API keys, report text, or location data into logs
or chat. This prototype must continue using fictional test data only.
