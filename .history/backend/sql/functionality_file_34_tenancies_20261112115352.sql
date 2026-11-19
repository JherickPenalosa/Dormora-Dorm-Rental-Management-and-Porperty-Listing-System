
-- DORMORA — SYSTEM FUNCTIONALITY FILE 34
-- CREATE: backend/sql/functionality_file_34_tenancies.sql
-- Execute in pgAdmin Query Tool with dormora_db selected.
-- Adds a tenancy record for formally assigned renters.
-- Does NOT auto-assign accepted inquiries or change room counts.
-- Existing users, properties, inquiries, messages, and photos are preserved.

BEGIN;

CREATE TABLE IF NOT EXISTS public.dorm_tenancies (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- The accepted inquiry that led to this tenancy. Each inquiry may be
    -- used for tenant assignment only once, even after the tenancy ends.
    inquiry_id BIGINT NOT NULL UNIQUE
        REFERENCES public.dorm_rental_inquiries(id) ON DELETE RESTRICT,

    property_id BIGINT NOT NULL
        REFERENCES public.dorm_properties(id) ON DELETE RESTRICT,

    renter_user_id BIGINT NOT NULL
        REFERENCES public.users(user_id) ON DELETE RESTRICT,

    -- An owner-provided identifier, e.g. "Room 101" or "Unit B-2".
    -- This is deliberately simpler than a separate room inventory table.
    room_label VARCHAR(60) NOT NULL,

    -- Snapshot the agreed rent rather than changing it whenever the
    -- property listing price is edited in the future.
    monthly_rent NUMERIC(12, 2) NOT NULL,
    rent_due_day SMALLINT NOT NULL DEFAULT 1,

    move_in_date DATE NOT NULL,
    move_out_date DATE,

    status VARCHAR(12) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ,

    CONSTRAINT dorm_tenancies_room_label_nonblank
        CHECK (LENGTH(BTRIM(room_label)) > 0),
    CONSTRAINT dorm_tenancies_rent_positive
        CHECK (monthly_rent > 0),
    CONSTRAINT dorm_tenancies_due_day_valid
        CHECK (rent_due_day BETWEEN 1 AND 28),
    CONSTRAINT dorm_tenancies_status_valid
        CHECK (status IN ('active', 'ended')),
    CONSTRAINT dorm_tenancies_date_order_valid
        CHECK (move_out_date IS NULL OR move_out_date >= move_in_date),
    CONSTRAINT dorm_tenancies_active_not_ended
        CHECK (status <> 'active' OR ended_at IS NULL),
    CONSTRAINT dorm_tenancies_ended_has_date
        CHECK (
            status <> 'ended'
            OR (move_out_date IS NOT NULL AND ended_at IS NOT NULL)
        )
);

-- Prevent two simultaneously active tenancies for the same room label
-- within a property (case-insensitive; ignores leading/trailing spaces).
CREATE UNIQUE INDEX IF NOT EXISTS uq_dorm_tenancies_active_room
    ON public.dorm_tenancies (
        property_id,
        LOWER(BTRIM(room_label))
    )
    WHERE status = 'active';

-- Keep the initial workflow simple: one active rental per renter.
CREATE UNIQUE INDEX IF NOT EXISTS uq_dorm_tenancies_active_renter
    ON public.dorm_tenancies (renter_user_id)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_dorm_tenancies_owner_property
    ON public.dorm_tenancies (property_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_dorm_tenancies_renter_history
    ON public.dorm_tenancies (renter_user_id, created_at DESC);

-- Runtime can read, create, and finish tenancies through authorized
-- backend services. No DELETE permission is added.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname = 'dormora_runtime'
    ) THEN
        GRANT SELECT, INSERT, UPDATE
            ON TABLE public.dorm_tenancies TO dormora_runtime;
    END IF;
END;
$$;

COMMIT;

-- Read-only verification. For a new table, tenancy_count is 0.
SELECT
    to_regclass('public.dorm_tenancies') AS tenancies_table,
    (SELECT COUNT(*) FROM public.dorm_tenancies) AS tenancy_count;
