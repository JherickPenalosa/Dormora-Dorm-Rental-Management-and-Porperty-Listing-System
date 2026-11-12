
-- DORMORA - SYSTEM FUNCTIONALITY FILE 28
-- CREATE: backend/sql/functionality_file_28_inquiry_messages.sql
-- Run using pgAdmin Query Tool connected to dormora_db.
-- Adds private inquiry replies without changing existing inquiry records.
-- Safe to rerun. No existing tables or rows are deleted or modified.

BEGIN;

CREATE TABLE IF NOT EXISTS public.dorm_inquiry_messages (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    inquiry_id BIGINT NOT NULL
        REFERENCES public.dorm_rental_inquiries(id) ON DELETE CASCADE,

    sender_user_id BIGINT NOT NULL
        REFERENCES public.users(user_id) ON DELETE CASCADE,

    message_text VARCHAR(1000) NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT dorm_inquiry_messages_nonblank_check
        CHECK (LENGTH(BTRIM(message_text)) > 0)
);

-- Retrieve a conversation chronologically and consistently.
CREATE INDEX IF NOT EXISTS idx_dorm_inquiry_messages_thread
    ON public.dorm_inquiry_messages (inquiry_id, created_at, id);

-- Optional future lookup for account-level message activity.
CREATE INDEX IF NOT EXISTS idx_dorm_inquiry_messages_sender
    ON public.dorm_inquiry_messages (sender_user_id, created_at DESC);

-- Application users need to read and append messages only.
-- Message editing and deletion are intentionally not granted.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname = 'dormora_runtime'
    ) THEN
        GRANT SELECT, INSERT
            ON TABLE public.dorm_inquiry_messages
            TO dormora_runtime;
    END IF;
END;
$$;

COMMIT;

-- Read-only verification of the newly created table.
SELECT
    to_regclass('public.dorm_inquiry_messages') AS messages_table,
    (SELECT COUNT(*) FROM public.dorm_inquiry_messages) AS message_count;
