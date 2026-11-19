
BEGIN;

DO $$
BEGIN
    IF current_database() <> 'dormora_db' THEN
        RAISE EXCEPTION 'File 131 must run in dormora_db';
    END IF;

    IF current_user <> 'postgres' THEN
        RAISE EXCEPTION 'File 131 requires the postgres administrator account';
    END IF;

    IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'dormora_runtime') THEN
        RAISE EXCEPTION 'dormora_runtime already exists; stop rather than modify an unknown role';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_catalog.pg_roles o ON o.oid = c.relowner
        WHERE n.nspname = 'public'
          AND c.relname = 'security_logs'
          AND c.relkind IN ('r', 'p')
          AND o.rolname = 'postgres'
    ) THEN
        RAISE EXCEPTION 'Expected postgres-owned public.security_logs table not found';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        CROSS JOIN LATERAL pg_catalog.aclexplode(
            COALESCE(c.relacl, pg_catalog.acldefault('r', c.relowner))
        ) a
        WHERE n.nspname = 'public'
          AND c.relname = 'security_logs'
          AND a.grantee = 0
          AND a.privilege_type IN ('UPDATE', 'DELETE', 'TRUNCATE', 'TRIGGER')
    ) THEN
        RAISE EXCEPTION 'security_logs has dangerous PUBLIC grants; review before creating a runtime role';
    END IF;

    CREATE ROLE dormora_runtime WITH NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT PASSWORD NULL;
END;
$$;

GRANT CONNECT ON DATABASE dormora_db TO dormora_runtime;
GRANT USAGE ON SCHEMA public TO dormora_runtime;

DO $$
DECLARE
    item record;
BEGIN
    FOR item IN
        SELECT c.relname
        FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relkind IN ('r', 'p')
          AND c.relname <> 'security_logs'
    LOOP
        EXECUTE format(
            'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.%I TO dormora_runtime',
            item.relname
        );
    END LOOP;

    FOR item IN
        SELECT c.relname
        FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relkind IN ('v', 'm')
    LOOP
        EXECUTE format(
            'GRANT SELECT ON TABLE public.%I TO dormora_runtime',
            item.relname
        );
    END LOOP;

    FOR item IN
        SELECT c.relname
        FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relkind = 'S'
    LOOP
        EXECUTE format(
            'GRANT USAGE, SELECT ON SEQUENCE public.%I TO dormora_runtime',
            item.relname
        );
    END LOOP;
END;
$$;

GRANT SELECT, INSERT ON TABLE public.security_logs TO dormora_runtime;

DO $$
BEGIN
    IF NOT has_table_privilege('dormora_runtime', 'public.security_logs', 'SELECT')
       OR NOT has_table_privilege('dormora_runtime', 'public.security_logs', 'INSERT')
       OR has_table_privilege('dormora_runtime', 'public.security_logs', 'UPDATE')
       OR has_table_privilege('dormora_runtime', 'public.security_logs', 'DELETE')
       OR has_table_privilege('dormora_runtime', 'public.security_logs', 'TRUNCATE')
       OR has_table_privilege('dormora_runtime', 'public.security_logs', 'TRIGGER')
       OR has_schema_privilege('dormora_runtime', 'public', 'CREATE')
       OR has_database_privilege('dormora_runtime', 'dormora_db', 'CREATE')
       OR pg_has_role('dormora_runtime', 'postgres', 'MEMBER')
       OR (SELECT rolcanlogin OR rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls
           FROM pg_catalog.pg_roles WHERE rolname = 'dormora_runtime')
    THEN
        RAISE EXCEPTION 'dormora_runtime failed least-privilege checks; transaction aborted';
    END IF;
END;
$$;

COMMIT;

SELECT
    r.rolname AS runtime_role,
    r.rolcanlogin AS login_enabled,
    r.rolsuper AS superuser,
    has_table_privilege(r.rolname, 'public.security_logs', 'SELECT') AS logs_select,
    has_table_privilege(r.rolname, 'public.security_logs', 'INSERT') AS logs_insert,
    has_table_privilege(r.rolname, 'public.security_logs', 'UPDATE') AS logs_update,
    has_table_privilege(r.rolname, 'public.security_logs', 'DELETE') AS logs_delete,
    has_table_privilege(r.rolname, 'public.security_logs', 'TRUNCATE') AS logs_truncate,
    has_schema_privilege(r.rolname, 'public', 'CREATE') AS schema_create
FROM pg_catalog.pg_roles r
WHERE r.rolname = 'dormora_runtime';
