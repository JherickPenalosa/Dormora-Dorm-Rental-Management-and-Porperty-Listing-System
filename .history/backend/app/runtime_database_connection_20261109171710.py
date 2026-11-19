
"""Dormora FullStack 3 - File 132: safe PostgreSQL runtime-role switch.

REPLACE: backend/app/runtime_database_connection.py (corrected File 132)

    python -m app.runtime_database_connection --check
    python -m app.runtime_database_connection --switch

File 131 has already created dormora_runtime with NOLOGIN and appropriate
security_logs grants. In pgAdmin, set a strong password for that role and
change Can login to Yes before running --switch. Never paste the password into
SQL, .py files, PowerShell commands, Git, or ChatGPT; --switch prompts without
terminal echo.

--check reads only PostgreSQL role metadata. --switch verifies the restricted
role's privileges, runs Dormora File 129's existing READ-ONLY local login and
recovery preflight in a subprocess using the new URL, and only then atomically
updates backend/.env. It supports existing .env files with zero or one
DATABASE_URL assignment. After writing, it requires an independently verified
connection as dormora_runtime with restricted log permissions; otherwise it
rolls back the .env change. Normal FastAPI processes must be restarted manually.

The script never grants privileges, changes a PostgreSQL role, or writes any
rows. It does not print connection strings or credentials. Keep migrations and
schema changes under a separate administrative connection, not the runtime.
"""

from __future__ import annotations

import argparse
import getpass
import ipaddress
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BACKEND = Path(__file__).resolve().parent.parent
ENV_FILE = BACKEND / ".env"
RUNTIME_USER = "dormora_runtime"
ENV_ASSIGNMENT = re.compile(
    r"^(?P<prefix>[ \t]*DATABASE_URL[ \t]*=[ \t]*)(?P<value>[^\r\n]*)(?P<end>\r?\n?)$",
    re.I,
)


class RuntimeSwitchError(RuntimeError):
    """Do not switch connection unless every prerequisite is satisfied."""


def _local_target():
    from app.core.config import settings
    from app.db.database import engine

    if settings.environment != "development":
        raise RuntimeSwitchError("Development environment required.")

    url = engine.url

    if engine.dialect.name != "postgresql" or url.database != "dormora_db":
        raise RuntimeSwitchError("Expected PostgreSQL dormora_db.")

    host = url.host or ""

    try:
        loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = host.casefold() == "localhost"

    if not loopback:
        raise RuntimeSwitchError("PostgreSQL must be on localhost/loopback.")

    return engine


def _role_metadata(engine) -> dict[str, bool]:
    query = text("""
        SELECT r.rolcanlogin AS can_login, r.rolsuper AS superuser,
               r.rolcreatedb AS create_db, r.rolcreaterole AS create_role,
               r.rolreplication AS replication, r.rolbypassrls AS bypass_rls,
               pg_has_role(:role, 'postgres', 'MEMBER') AS postgres_member,
               has_table_privilege(:role, 'public.security_logs', 'SELECT') AS log_read,
               has_table_privilege(:role, 'public.security_logs', 'INSERT') AS log_insert,
               has_table_privilege(:role, 'public.security_logs', 'UPDATE') AS log_update,
               has_table_privilege(:role, 'public.security_logs', 'DELETE') AS log_delete,
               has_table_privilege(:role, 'public.security_logs', 'TRUNCATE') AS log_truncate,
               has_table_privilege(:role, 'public.security_logs', 'TRIGGER') AS log_trigger,
               has_schema_privilege(:role, 'public', 'CREATE') AS schema_create
        FROM pg_catalog.pg_roles AS r WHERE r.rolname = :role
    """)

    try:
        with engine.connect() as conn:
            with conn.begin():
                conn.execute(text("SET TRANSACTION READ ONLY"))
                row = conn.execute(
                    query, {"role": RUNTIME_USER}
                ).mappings().one_or_none()
    except Exception as exc:
        raise RuntimeSwitchError(
            "Could not inspect runtime role metadata."
        ) from exc

    if row is None:
        raise RuntimeSwitchError(
            "Role dormora_runtime is missing; complete File 131."
        )

    result = dict(row)

    if any(type(value) is not bool for value in result.values()):
        raise RuntimeSwitchError(
            "Unexpected runtime role privilege metadata."
        )

    return result


def _require_safe_role(role: dict[str, bool], *, login: bool) -> None:
    expected_true = ("log_read", "log_insert")
    forbidden = (
        "superuser", "create_db", "create_role", "replication",
        "bypass_rls", "postgres_member", "log_update", "log_delete",
        "log_truncate", "log_trigger", "schema_create",
    )

    if any(not role.get(name, False) for name in expected_true):
        raise RuntimeSwitchError(
            "Runtime role cannot both read and insert audit rows."
        )

    if any(role.get(name, True) for name in forbidden):
        raise RuntimeSwitchError(
            "Runtime role has an unsafe elevated privilege."
        )

    if login and not role.get("can_login", False):
        raise RuntimeSwitchError(
            "Role is still NOLOGIN: enable login and set its password in pgAdmin."
        )


def _verify_runtime_connection(url) -> None:
    """Inspect effective permissions without modifying any database rows."""
    probe = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 5},
    )

    try:
        with probe.connect() as conn:
            with conn.begin():
                conn.execute(text("SET TRANSACTION READ ONLY"))

                sql = text("""
                    SELECT current_user AS who,
                      has_table_privilege(current_user, 'public.security_logs', 'SELECT') AS sr,
                      has_table_privilege(current_user, 'public.security_logs', 'INSERT') AS si,
                      has_table_privilege(current_user, 'public.security_logs', 'UPDATE') AS su,
                      has_table_privilege(current_user, 'public.security_logs', 'DELETE') AS sd,
                      has_table_privilege(current_user, 'public.security_logs', 'TRUNCATE') AS st,
                      has_schema_privilege(current_user, 'public', 'CREATE') AS sc,
                      (SELECT count(*) FROM pg_catalog.pg_class c
                       JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
                       WHERE n.nspname='public' AND c.relkind IN ('r','p')
                         AND c.relname <> 'security_logs'
                         AND NOT (has_table_privilege(current_user,c.oid,'SELECT')
                              AND has_table_privilege(current_user,c.oid,'INSERT')
                              AND has_table_privilege(current_user,c.oid,'UPDATE')
                              AND has_table_privilege(current_user,c.oid,'DELETE'))
                      ) AS missing_table_grants,
                      (SELECT count(*) FROM pg_catalog.pg_class c
                       JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
                       WHERE n.nspname='public' AND c.relkind='S'
                         AND NOT has_sequence_privilege(current_user,c.oid,'USAGE')
                      ) AS missing_sequence_grants
                """)

                item = conn.execute(sql).mappings().one()

                if (
                    item["who"] != RUNTIME_USER
                    or not item["sr"]
                    or not item["si"]
                    or item["su"]
                    or item["sd"]
                    or item["st"]
                    or item["sc"]
                    or item["missing_table_grants"] != 0
                    or item["missing_sequence_grants"] != 0
                ):
                    raise RuntimeSwitchError(
                        "Runtime privileges do not match the File 131 grants."
                    )

    except RuntimeSwitchError:
        raise
    except Exception as exc:
        raise RuntimeSwitchError(
            "Runtime credential login or SQL permission probe failed."
        ) from exc
    finally:
        probe.dispose()


def _new_env_content(original: bytes, url) -> bytes:
    """Replace one or append a missing DATABASE_URL, preserving other secrets.

    Legacy Dormora setups can derive their initial DB URL without a named
    DATABASE_URL line. The post-write role check prevents a false success if
    that newly appended setting is not honored by the configuration loader.
    """
    try:
        data = original.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise RuntimeSwitchError(
            "backend/.env must be UTF-8."
        ) from exc

    lines = data.splitlines(keepends=True)

    hits = [
        (index, ENV_ASSIGNMENT.fullmatch(line))
        for index, line in enumerate(lines)
    ]
    hits = [
        (index, match)
        for index, match in hits
        if match is not None
    ]

    if len(hits) > 1:
        raise RuntimeSwitchError(
            "backend/.env contains duplicate DATABASE_URL assignments; "
            "remove the duplicate manually without sharing the values."
        )

    rendered = url.render_as_string(hide_password=False)

    if any(c.isspace() for c in rendered) or "#" in rendered:
        raise RuntimeSwitchError(
            "New URL could not be encoded safely for .env."
        )

    if not hits:
        if any(
            re.match(
                r"^[ \t]*(?:export[ \t]+)?DATABASE_URL\b",
                line,
                re.I,
            )
            for line in lines
        ):
            raise RuntimeSwitchError(
                "backend/.env has a nonstandard DATABASE_URL assignment; "
                "review its key formatting without sharing its value."
            )

        newline = "\r\n" if "\r\n" in data else "\n"

        if data and not data.endswith(("\n", "\r")):
            data += newline

        return (
            data + "DATABASE_URL=" + rendered + newline
        ).encode("utf-8")

    index, match = hits[0]
    old = match.group("value").strip()

    if old.startswith(('"', "'")) and old[-1:] == old[:1]:
        old = old[1:-1]

    try:
        current = make_url(old)
    except Exception as exc:
        raise RuntimeSwitchError(
            "Could not parse existing .env DATABASE_URL."
        ) from exc

    if current.username != "postgres" or current.database != "dormora_db":
        raise RuntimeSwitchError(
            "Expected the existing postgres DB URL before switching."
        )

    lines[index] = (
        match.group("prefix") + rendered + match.group("end")
    )

    return "".join(lines).encode("utf-8")


def _atomic_env_write(data: bytes) -> None:
    if not ENV_FILE.is_file() or ENV_FILE.is_symlink():
        raise RuntimeSwitchError(
            "backend/.env is missing or a symbolic link."
        )

    fd, temporary = tempfile.mkstemp(
        prefix=".env.file132-",
        suffix=".tmp",
        dir=BACKEND,
    )

    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())

        try:
            os.chmod(
                temporary,
                ENV_FILE.stat().st_mode & 0o777,
            )
        except OSError:
            pass

        os.replace(temporary, ENV_FILE)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _preflight(url_override: str | None) -> bool:
    """Require both the old security preflight and proof of the active DB role.

    A previous version only checked whether the API routes loaded. That could
    pass while FastAPI was still connected as postgres. This version also runs
    the independent File 130 effective-role audit and rejects that scenario.
    """
    environment = os.environ.copy()
    environment.pop("DATABASE_URL", None)

    if url_override is not None:
        environment["DATABASE_URL"] = url_override

    def _run(module: str, required_text: tuple[str, ...]) -> bool:
        try:
            result = subprocess.run(
                [sys.executable, "-m", module, "--check"],
                cwd=BACKEND,
                env=environment,
                capture_output=True,
                text=True,
                timeout=75,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False

        return result.returncode == 0 and all(
            marker in result.stdout for marker in required_text
        )

    if not _run(
        "app.local_password_recovery_runner",
        ("File 129 check OK",),
    ):
        return False

    return _run(
        "app.security_log_permissions",
        (
            "Backend effective role: dormora_runtime",
            "Append-only permission assessment: PRIVILEGES RESTRICTED",
            "File 130 check OK",
        ),
    )


def _env_safe_to_edit() -> bytes:
    if "DATABASE_URL" in os.environ:
        raise RuntimeSwitchError(
            "DATABASE_URL is set in the current shell; remove that override first."
        )

    if not ENV_FILE.is_file() or ENV_FILE.is_symlink():
        raise RuntimeSwitchError(
            "Expected a regular backend/.env file."
        )

    repo = BACKEND.parent

    try:
        relative = str(ENV_FILE.relative_to(repo))

        tracked = subprocess.run(
            [
                "git", "-C", str(repo),
                "ls-files", "--error-unmatch", "--", relative,
            ],
            capture_output=True,
            timeout=5,
            check=False,
        )

        ignored = subprocess.run(
            [
                "git", "-C", str(repo),
                "check-ignore", "-q", "--", relative,
            ],
            capture_output=True,
            timeout=5,
            check=False,
        )

    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeSwitchError(
            "Could not verify that .env is excluded from Git."
        ) from exc

    if tracked.returncode == 0 or ignored.returncode != 0:
        raise RuntimeSwitchError(
            "backend/.env may be Git-tracked; refusing to write credentials."
        )

    return ENV_FILE.read_bytes()


def _switch(engine) -> None:
    if engine.url.username != "postgres":
        raise RuntimeSwitchError(
            "Expected current backend connection as postgres before switching."
        )

    role = _role_metadata(engine)
    _require_safe_role(role, login=True)
    original = _env_safe_to_edit()

    password = getpass.getpass(
        "Enter dormora_runtime password (hidden): "
    )
    confirmation = getpass.getpass(
        "Re-enter password (hidden): "
    )

    if not (
        password == confirmation
        and len(password) >= 16
        and all(33 <= ord(c) <= 126 for c in password)
    ):
        raise RuntimeSwitchError(
            "Passwords must match and use at least 16 non-space ASCII characters."
        )

    new_url = engine.url.set(
        username=RUNTIME_USER,
        password=password,
    )

    _verify_runtime_connection(new_url)

    printed_url = new_url.render_as_string(
        hide_password=False
    )

    if not _preflight(printed_url):
        raise RuntimeSwitchError(
            "File 129 preflight failed under the restricted role; .env unchanged."
        )

    changed = _new_env_content(original, new_url)

    try:
        _atomic_env_write(changed)

        if not _preflight(None):
            raise RuntimeSwitchError(
                ".env reload did not pass File 129 AND restricted-role File 130; "
                "restoring the original .env. Check how app/db/database.py reads DATABASE_URL."
            )

    except BaseException:
        if ENV_FILE.read_bytes() != original:
            _atomic_env_write(original)
        raise
    finally:
        password = ""
        confirmation = ""
        printed_url = ""

    print("DORMORA FILE 132 -- RUNTIME DB CONNECTION SWITCH")
    print("Restricted-role connection: PASS")
    print(
        "Audit SELECT/INSERT allowed; UPDATE/DELETE/TRUNCATE denied: PASS"
    )
    print(
        "File 129 login/recovery and File 130 effective-role preflights: PASS"
    )
    print(
        "backend/.env updated safely (URL/password not displayed)"
    )
    print(
        "Restart FastAPI and re-run File 130 to confirm the new effective role."
    )
    print("File 132 switch OK")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dormora local runtime DB role switch"
    )

    mode = parser.add_mutually_exclusive_group(required=True)

    mode.add_argument(
        "--check",
        action="store_true",
        help="Read-only role readiness check",
    )
    mode.add_argument(
        "--switch",
        action="store_true",
        help="Verify and securely change backend/.env",
    )

    args = parser.parse_args()

    try:
        engine = _local_target()

        if args.check:
            role = _role_metadata(engine)
            _require_safe_role(role, login=False)

            print("DORMORA FILE 132 -- RUNTIME ROLE READINESS")
            print(
                "Role: dormora_runtime | Existing File 131 grants: PASS"
            )
            print(
                "Can login:",
                "YES" if role["can_login"] else "NO (not activated yet)",
            )
            print(
                "Current application connection:",
                engine.url.username,
            )

            if ENV_FILE.is_file() and not ENV_FILE.is_symlink():
                env_lines = ENV_FILE.read_text(
                    encoding="utf-8-sig"
                ).splitlines(keepends=True)

                count = sum(
                    ENV_ASSIGNMENT.fullmatch(line) is not None
                    for line in env_lines
                )

                print(
                    "backend/.env DATABASE_URL entries:",
                    count,
                )
                print(
                    "Missing entry will be appended only "
                    "after all switch prechecks pass."
                )

            print(
                "No database role, credentials, or .env file changed."
            )
            print("File 132 check OK")
        else:
            _switch(engine)

    except RuntimeSwitchError as exc:
        print("FILE 132 STOPPED:", str(exc))
        raise SystemExit(1) from None
    except Exception as exc:
        print("FILE 132 FAILED:", type(exc).__name__)
        print("No connection details or password will be displayed.")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
