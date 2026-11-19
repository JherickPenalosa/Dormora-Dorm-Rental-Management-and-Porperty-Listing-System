
-- DORMORA — SYSTEM FUNCTIONALITY FILE 42
-- CREATE: backend/sql/functionality_file_42_rent_management.sql
-- Run in pgAdmin Query Tool connected to dormora_db.
-- Re-runnable without deleting or resetting existing records.
--
-- Purpose:
--   1. One monthly rent charge per tenancy and billing month.
--   2. Owner-recorded payments, including partial payments.
--   3. Read-only balances/status calculated from charges + payments.
--
-- This file does NOT generate rent charges, record a payment, process an
-- online transaction, or change any tenancy/room availability records.
-- Those actions will be implemented through authenticated backend services.

BEGIN;

-- A charge captures the agreed monthly rent for a specific billing month.
-- Future service logic must verify that the charge belongs to a valid
-- tenancy and that its billing month is within that tenancy's rental period.
CREATE TABLE IF NOT EXISTS public.dorm_rent_charges (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    tenancy_id BIGINT NOT NULL
        REFERENCES public.dorm_tenancies(id) ON DELETE RESTRICT,

    billing_month DATE NOT NULL,
    due_date DATE NOT NULL,
    amount_due NUMERIC(12, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT dorm_rent_charges_one_per_month
        UNIQUE (tenancy_id, billing_month),

    CONSTRAINT dorm_rent_charges_month_first_day
        CHECK (EXTRACT(DAY FROM billing_month) = 1),

    CONSTRAINT dorm_rent_charges_due_in_billing_month
        CHECK (
            due_date >= billing_month
            AND due_date < (billing_month + INTERVAL '1 month')::DATE
        ),

    CONSTRAINT dorm_rent_charges_amount_positive
        CHECK (amount_due > 0)
);

-- A rent charge may have multiple partial payments. Each payment records
-- an amount reportedly received by the owner; it is not an online transfer.
CREATE TABLE IF NOT EXISTS public.dorm_rent_payments (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    charge_id BIGINT NOT NULL
        REFERENCES public.dorm_rent_charges(id) ON DELETE RESTRICT,

    recorded_by_user_id BIGINT NOT NULL
        REFERENCES public.users(user_id) ON DELETE RESTRICT,

    amount NUMERIC(12, 2) NOT NULL,
    payment_method VARCHAR(20) NOT NULL,
    paid_on DATE NOT NULL,
    reference_note VARCHAR(200),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT dorm_rent_payments_amount_positive
        CHECK (amount > 0),

    CONSTRAINT dorm_rent_payments_method_valid
        CHECK (payment_method IN (
            'cash', 'bank_transfer', 'e_wallet', 'other'
        )),

    CONSTRAINT dorm_rent_payments_note_nonblank
        CHECK (
            reference_note IS NULL
            OR LENGTH(BTRIM(reference_note)) > 0
        )
);

-- Efficient owner/renter rent-history lookups through the tenancy ID.
CREATE INDEX IF NOT EXISTS idx_dorm_rent_charges_tenancy_month
    ON public.dorm_rent_charges (tenancy_id, billing_month DESC);

CREATE INDEX IF NOT EXISTS idx_dorm_rent_charges_due_date
    ON public.dorm_rent_charges (due_date);

CREATE INDEX IF NOT EXISTS idx_dorm_rent_payments_charge_date
    ON public.dorm_rent_payments (charge_id, paid_on DESC, id DESC);

-- Calculate balances at read time so payment statuses cannot go stale.
-- For an unpaid balance past its due date, 'overdue' takes precedence over
-- 'partially_paid'; the total_paid field still shows partial payments.
-- Date calculations use Philippine local time, not the DB server timezone.
CREATE OR REPLACE VIEW public.dorm_rent_balances AS
WITH charge_totals AS (
    SELECT
        c.id AS charge_id,
        c.tenancy_id,
        c.billing_month,
        c.due_date,
        c.amount_due,
        c.created_at,
        COALESCE(SUM(p.amount), 0::NUMERIC) AS total_paid
    FROM public.dorm_rent_charges AS c
    LEFT JOIN public.dorm_rent_payments AS p
        ON p.charge_id = c.id
    GROUP BY
        c.id,
        c.tenancy_id,
        c.billing_month,
        c.due_date,
        c.amount_due,
        c.created_at
)
SELECT
    charge_id,
    tenancy_id,
    billing_month,
    due_date,
    amount_due,
    total_paid,
    amount_due - total_paid AS balance_due,
    CASE
        WHEN total_paid >= amount_due THEN 'paid'
        WHEN due_date < (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Manila')::DATE
            THEN 'overdue'
        WHEN total_paid > 0 THEN 'partially_paid'
        ELSE 'pending'
    END AS payment_status,
    created_at
FROM charge_totals;

-- Give Dormora's restricted database role only the permissions required
-- by the planned backend service. No UPDATE/DELETE grant on payment rows:
-- corrections/reversals need a separate, auditable workflow if added later.
DO $$
DECLARE
    charge_sequence TEXT;
    payment_sequence TEXT;
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname = 'dormora_runtime'
    ) THEN
        GRANT SELECT, INSERT ON TABLE
            public.dorm_rent_charges,
            public.dorm_rent_payments
            TO dormora_runtime;

        GRANT SELECT ON TABLE public.dorm_rent_balances
            TO dormora_runtime;

        charge_sequence := pg_get_serial_sequence(
            'public.dorm_rent_charges', 'id'
        );
        payment_sequence := pg_get_serial_sequence(
            'public.dorm_rent_payments', 'id'
        );

        IF charge_sequence IS NOT NULL THEN
            EXECUTE format(
                'GRANT USAGE ON SEQUENCE %s TO dormora_runtime',
                charge_sequence::REGCLASS
            );
        END IF;
        IF payment_sequence IS NOT NULL THEN
            EXECUTE format(
                'GRANT USAGE ON SEQUENCE %s TO dormora_runtime',
                payment_sequence::REGCLASS
            );
        END IF;
    END IF;
END;
$$;

COMMIT;

-- READ-ONLY VERIFICATION: newly created tables should each have 0 rows.
SELECT
    to_regclass('public.dorm_rent_charges') AS charges_table,
    to_regclass('public.dorm_rent_payments') AS payments_table,
    to_regclass('public.dorm_rent_balances') AS balances_view,
    (SELECT COUNT(*) FROM public.dorm_rent_charges) AS charge_count,
    (SELECT COUNT(*) FROM public.dorm_rent_payments) AS payment_count;
