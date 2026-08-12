#!/usr/bin/env python3
"""Independent privilege-boundary gate for the alt-data PIT archive (h4).

Authored by Jarvis (authority layer), not by the executing agent, after the ECC
FAIL at ba0ad3c and the auditor CRITICAL of 2026-08-12.  It answers one question
that the phase cannot self-certify:

    Can the credential the running services actually use rewrite a vintage?

It deliberately does NOT trust a role name supplied on the command line: the
role under test is read from the live containers' ``DATABASE_URL``.  A design
that blocks an arbitrary hand-made role while the services still connect as a
superuser passes no gate here.

Every probe runs inside an aborted transaction, so the gate never mutates the
archive.

Exit 0  = boundary holds.
Exit 1  = boundary broken (details on stdout).
Exit 2  = the gate could not establish ground truth (never treat as a pass).
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit

DB_CONTAINER_DEFAULT = "ib_bot-db-1"
SERVICE_CONTAINERS_DEFAULT = ("ib_bot-api-1", "ib_bot-worker-1", "ib_bot-beat-1")

SNAPSHOTS = "altdata_snapshots"
CORRECTIONS = "altdata_snapshot_corrections"

# Each negative must be REJECTED. The first element is the label, the second the
# SQL body executed inside a transaction that is never committed.
NEGATIVES: list[tuple[str, str]] = [
    (
        "forged-capability-update",
        # Mint a correction row that matches the trigger's binding conditions and
        # then perform the raw UPDATE it authorises. This is the ECC finding.
        f"""
        INSERT INTO {CORRECTIONS}
          (snapshot_id, actor, reason, old_n_rows, old_content_hash, old_payload,
           new_n_rows, new_content_hash, new_payload, correction_nonce, correction_txid)
        SELECT id, 'privilege-gate', 'forged capability probe', n_rows, content_hash, payload,
               n_rows + 1, 'forged', payload,
               md5(random()::text || clock_timestamp()::text)::uuid, txid_current()
        FROM {SNAPSHOTS} ORDER BY id LIMIT 1;
        SELECT set_config('ib_bot.altdata_authorized_correction',
                          (SELECT correction_nonce::text FROM {CORRECTIONS}
                           ORDER BY id DESC LIMIT 1), true);
        UPDATE {SNAPSHOTS} SET n_rows = n_rows + 1, content_hash = 'forged'
        WHERE id = (SELECT min(id) FROM {SNAPSHOTS});
        """,
    ),
    (
        "session-replication-role-bypass",
        # A superuser silences row triggers with one SET. No trigger design
        # survives this, which is why the app credential must not be superuser.
        f"""
        SET session_replication_role = replica;
        UPDATE {SNAPSHOTS} SET n_rows = n_rows + 1 WHERE id = (SELECT min(id) FROM {SNAPSHOTS});
        """,
    ),
    (
        "disable-trigger-bypass",
        # Table ownership alone is enough to switch the guard off.
        f"""
        ALTER TABLE {SNAPSHOTS} DISABLE TRIGGER ALL;
        UPDATE {SNAPSHOTS} SET n_rows = n_rows + 1 WHERE id = (SELECT min(id) FROM {SNAPSHOTS});
        """,
    ),
    (
        "raw-update",
        f"UPDATE {SNAPSHOTS} SET n_rows = n_rows + 1 WHERE id = (SELECT min(id) FROM {SNAPSHOTS});",
    ),
    (
        "raw-delete",
        f"DELETE FROM {SNAPSHOTS} WHERE id = (SELECT min(id) FROM {SNAPSHOTS});",
    ),
    (
        "correction-ledger-insert",
        # The ledger is the capability store; the app must not be able to write it.
        f"""
        INSERT INTO {CORRECTIONS}
          (snapshot_id, actor, reason, old_n_rows, old_content_hash, old_payload,
           new_n_rows, new_content_hash, new_payload, correction_nonce, correction_txid)
        SELECT id, 'privilege-gate', 'ledger write probe', n_rows, content_hash, payload,
               n_rows, content_hash, payload,
               md5(random()::text || clock_timestamp()::text)::uuid, txid_current()
        FROM {SNAPSHOTS} ORDER BY id LIMIT 1;
        """,
    ),
]

# Each positive must SUCCEED: the boundary is worthless if it breaks the daily
# collector or the chain verifier.
POSITIVES: list[tuple[str, str]] = [
    (
        "collector-append",
        f"""
        INSERT INTO {SNAPSHOTS} (source, as_of_date, captured_at, n_rows, content_hash, payload)
        VALUES ('__privilege_gate_probe__', DATE '1999-01-01', now(), 1, 'probe', '{{"probe":1}}'::jsonb);
        """,
    ),
    ("read-snapshots", f"SELECT count(*) FROM {SNAPSHOTS};"),
    ("read-corrections", f"SELECT count(*) FROM {CORRECTIONS};"),
]


def run(cmd: list[str], stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, input=stdin, capture_output=True, text=True)


def service_dsn(container: str) -> str | None:
    proc = run(["docker", "exec", container, "printenv", "DATABASE_URL"])
    return proc.stdout.strip() or None


def parse_dsn(dsn: str) -> tuple[str, str, str]:
    """Return (user, password, dbname) from a SQLAlchemy or libpq URL."""
    plain = re.sub(r"^postgresql\+[a-z0-9]+://", "postgresql://", dsn)
    parts = urlsplit(plain)
    return (
        unquote(parts.username or ""),
        unquote(parts.password or ""),
        (parts.path or "/").lstrip("/"),
    )


def psql(db_container: str, user: str, password: str, dbname: str, sql: str) -> subprocess.CompletedProcess:
    url = f"postgresql://{user}:{password}@127.0.0.1:5432/{dbname}"
    return run(
        ["docker", "exec", "-i", "-e", "PSQL_TARGET=" + url, db_container,
         "psql", url, "-v", "ON_ERROR_STOP=1", "-X", "-q", "-f", "-"],
        stdin=f"BEGIN;\n{sql}\nROLLBACK;\n",
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-container", default=DB_CONTAINER_DEFAULT)
    ap.add_argument("--service-containers", nargs="*", default=list(SERVICE_CONTAINERS_DEFAULT))
    ap.add_argument(
        "--dsn",
        help="Override the credential under test. Only for rehearsing the gate "
             "against a scratch database; a real run must read the services.",
    )
    args = ap.parse_args()

    failures: list[str] = []

    if args.dsn:
        dsn = args.dsn
        print(f"[warn] credential supplied on the command line: {parse_dsn(dsn)[0]} (rehearsal mode)")
    else:
        seen: dict[str, list[str]] = {}
        for container in args.service_containers:
            got = service_dsn(container)
            if not got:
                print(f"[gate] cannot read DATABASE_URL from {container}")
                return 2
            seen.setdefault(got, []).append(container)
        if len(seen) != 1:
            print("[gate] services disagree on DATABASE_URL:")
            for value, containers in seen.items():
                print(f"  {parse_dsn(value)[0]} <- {', '.join(containers)}")
            return 1
        dsn = next(iter(seen))
        print(f"[gate] credential under test comes from {', '.join(args.service_containers)}")

    user, password, dbname = parse_dsn(dsn)
    if not user or not dbname:
        print(f"[gate] unparseable DATABASE_URL: {dsn}")
        return 2
    print(f"[gate] role={user} db={dbname}")

    attrs = run([
        "docker", "exec", args.db_container, "psql", "-U", user, "-d", dbname, "-At", "-F", "|",
        "-c",
        "SELECT rolsuper, rolbypassrls, rolcreaterole, rolcreatedb FROM pg_roles WHERE rolname = current_user;",
    ])
    if attrs.returncode != 0 or not attrs.stdout.strip():
        print(f"[gate] cannot read role attributes: {attrs.stderr.strip()}")
        return 2
    rolsuper, rolbypassrls, rolcreaterole, rolcreatedb = (
        v == "t" for v in attrs.stdout.strip().split("|")
    )
    print(
        f"[attr] superuser={rolsuper} bypassrls={rolbypassrls} "
        f"createrole={rolcreaterole} createdb={rolcreatedb}"
    )
    if rolsuper:
        failures.append(
            "role is a superuser: every REVOKE, trigger and ownership boundary is void for it"
        )
    if rolbypassrls or rolcreaterole or rolcreatedb:
        failures.append("role holds CREATEROLE/CREATEDB/BYPASSRLS, which can re-acquire the boundary")

    owners = run([
        "docker", "exec", args.db_container, "psql", "-U", user, "-d", dbname, "-At", "-F", "|",
        "-c",
        "SELECT c.relname, pg_get_userbyid(c.relowner) FROM pg_class c "
        f"WHERE c.relname IN ('{SNAPSHOTS}', '{CORRECTIONS}') ORDER BY 1;",
    ])
    for line in owners.stdout.strip().splitlines():
        relname, owner = line.split("|")
        print(f"[own] {relname} owner={owner}")
        if owner == user:
            failures.append(f"{relname} is owned by the application role: it can disable its own guard")

    for label, sql in NEGATIVES:
        proc = psql(args.db_container, user, password, dbname, sql)
        rejected = proc.returncode != 0
        detail = (proc.stderr.strip().splitlines() or [""])[0]
        print(f"[neg] {label}: {'REJECTED' if rejected else 'ACCEPTED'} :: {detail}")
        if not rejected:
            failures.append(f"negative '{label}' succeeded against the live credential")

    for label, sql in POSITIVES:
        proc = psql(args.db_container, user, password, dbname, sql)
        ok = proc.returncode == 0
        detail = (proc.stderr.strip().splitlines() or [""])[0]
        print(f"[pos] {label}: {'OK' if ok else 'BROKEN'} :: {detail}")
        if not ok:
            failures.append(f"positive '{label}' broke: the boundary is not service-compatible")

    if failures:
        print("\nGATE FAIL")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("\nGATE PASS: the live service credential cannot rewrite a vintage, and the collector still appends.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
