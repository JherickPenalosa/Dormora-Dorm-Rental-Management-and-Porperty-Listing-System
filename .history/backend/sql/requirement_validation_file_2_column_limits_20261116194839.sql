
-- DORMORA — REQUIREMENT VALIDATION FILE 2
-- CREATE: backend/sql/requirement_validation_file_2_column_limits.sql
-- Run in pgAdmin Query Tool connected to dormora_db.
-- Widens username/name columns without deleting existing records.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

DO $migration$
DECLARE
    target record;
    column_type text;
    column_limit integer;
    conflicting_constraint text;
BEGIN
    IF current_database() <> 'dormora_db' THEN
        RAISE EXCEPTION
            'Expected dormora_db, got %', current_database();
    END IF;

    -- Validate every expected column before making changes.
    FOR target IN
        SELECT * FROM (VALUES
            ('users', 'username', 20),
            ('user_profiles', 'first_name', 50),
            ('user_profiles', 'middle_name', 50),
            ('user_profiles', 'family_name', 50)
        ) AS expected(table_name, column_name, required_max)
    LOOP
        SELECT c.data_type, c.character_maximum_length
        INTO column_type, column_limit
        FROM information_schema.columns AS c
        WHERE c.table_schema = 'public'
          AND c.table_name = target.table_name
          AND c.column_name = target.column_name;

        IF NOT FOUND THEN
            RAISE EXCEPTION
                'Missing public.%.%; inspect schema first.',
                target.table_name, target.column_name;
        END IF;

        IF column_type NOT IN ('character varying', 'text') THEN
            RAISE EXCEPTION
                'Unexpected type % for public.%.%',
                column_type, target.table_name, target.column_name;
        END IF;

        -- Do not silently remove legacy CHECK constraints.
        SELECT con.conname
        INTO conflicting_constraint
        FROM pg_catalog.pg_constraint AS con
        JOIN pg_catalog.pg_class AS tab
            ON tab.oid = con.conrelid
        JOIN pg_catalog.pg_namespace AS ns
            ON ns.oid = tab.relnamespace
        WHERE ns.nspname = 'public'
          AND tab.relname = target.table_name
          AND con.contype = 'c'
          AND pg_get_constraintdef(con.oid)
              ILIKE '%' || target.column_name || '%'
          AND pg_get_constraintdef(con.oid)
              ~* '(length|char_length|character_length)'
          AND pg_get_constraintdef(con.oid)
              ~ '(^|[^0-9])(17|26)([^0-9]|$)'
        LIMIT 1;

        IF conflicting_constraint IS NOT NULL THEN
            RAISE EXCEPTION
                'Legacy length constraint % requires review.',
                conflicting_constraint;
        END IF;

        conflicting_constraint := NULL;

        RAISE NOTICE 'Checked public.%.%: limit %, required %',
            target.table_name,
            target.column_name,
            COALESCE(column_limit::text, 'unlimited'),
            target.required_max;
    END LOOP;

    -- Widen only columns smaller than the instructor's limits.
    FOR target IN
        SELECT * FROM (VALUES
            ('users', 'username', 20),
            ('user_profiles', 'first_name', 50),
            ('user_profiles', 'middle_name', 50),
            ('user_profiles', 'family_name', 50)
        ) AS expected(table_name, column_name, required_max)
    LOOP
        SELECT c.data_type, c.character_maximum_length
        INTO column_type, column_limit
        FROM information_schema.columns AS c
        WHERE c.table_schema = 'public'
          AND c.table_name = target.table_name
          AND c.column_name = target.column_name;

        IF column_type = 'character varying'
           AND column_limit IS NOT NULL
           AND column_limit < target.required_max THEN

            EXECUTE format(
                'ALTER TABLE public.%I ALTER COLUMN %I TYPE VARCHAR(%s)',
                target.table_name,
                target.column_name,
                target.required_max
            );

            RAISE NOTICE 'Widened public.%.% to VARCHAR(%)',
                target.table_name,
                target.column_name,
                target.required_max;
        ELSE
            RAISE NOTICE 'Already sufficient: public.%.%',
                target.table_name, target.column_name;
        END IF;
    END LOOP;
END
$migration$;

SELECT
    table_name,
    column_name,
    data_type,
    character_maximum_length
FROM information_schema.columns
WHERE table_schema = 'public'
  AND (
      (table_name = 'users' AND column_name = 'username')
      OR
      (table_name = 'user_profiles' AND column_name IN
          ('first_name', 'middle_name', 'family_name'))
  )
ORDER BY table_name, column_name;

COMMIT;
