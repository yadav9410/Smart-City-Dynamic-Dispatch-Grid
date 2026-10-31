-- Phase 16.9 rate-limit storage migration for Neon/PostgreSQL.
-- Run this in the Neon SQL Editor using the same database/branch referenced by
-- DATABASE_URL in Streamlit Cloud. It is idempotent and does not modify reports.

CREATE TABLE IF NOT EXISTS public.public_request_limits (
    session_hash CHAR(64) NOT NULL
        CHECK (session_hash ~ '^[0-9a-f]{64}$'),
    action VARCHAR(32) NOT NULL
        CHECK (action IN ('report_submit', 'audio_transcription', 'ai_assessment')),
    window_started_at TIMESTAMPTZ NOT NULL,
    request_count INTEGER NOT NULL CHECK (request_count BETWEEN 1 AND 1001),
    last_request_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (session_hash, action)
);

CREATE INDEX IF NOT EXISTS idx_public_request_limits_last_request
    ON public.public_request_limits (last_request_at);

-- Expected result: public.public_request_limits
SELECT to_regclass('public.public_request_limits') AS rate_limit_table;
