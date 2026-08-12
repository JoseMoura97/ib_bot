"""separate PIT archive ownership from the application database role

Revision ID: 0014_altdata_owner_separation
Revises: 0013_altdata_correction_audit_nonce
Create Date: 2026-08-12

``ibbot`` is the PostgreSQL bootstrap/admin role and must remain a superuser:
PostgreSQL rejects attempts to demote the bootstrap role, and doing so would
also make future Alembic migrations impossible.  The services therefore use a
separate, non-superuser login role while the protected archive is owned by a
no-login role.
"""
from alembic import op


revision = "0014_altdata_owner_separation"
down_revision = "0013_altdata_correction_audit_nonce"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ibbot_altdata_owner') THEN
                CREATE ROLE ibbot_altdata_owner NOLOGIN NOINHERIT NOSUPERUSER
                    NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
            END IF;
        END;
        $$;

        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ibbot_app') THEN
                CREATE ROLE ibbot_app LOGIN PASSWORD 'ibbot_app'
                    NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
            ELSE
                ALTER ROLE ibbot_app LOGIN PASSWORD 'ibbot_app'
                    NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
            END IF;
        END;
        $$;

        ALTER TABLE altdata_snapshots OWNER TO ibbot_altdata_owner;
        ALTER TABLE altdata_snapshot_corrections OWNER TO ibbot_altdata_owner;
        ALTER SEQUENCE altdata_snapshots_id_seq OWNER TO ibbot_altdata_owner;
        ALTER SEQUENCE altdata_snapshot_corrections_id_seq OWNER TO ibbot_altdata_owner;
        ALTER FUNCTION reject_altdata_snapshot_mutation() OWNER TO ibbot_altdata_owner;
        ALTER FUNCTION reject_altdata_snapshot_correction_mutation() OWNER TO ibbot_altdata_owner;
        ALTER FUNCTION apply_altdata_snapshot_correction(integer, integer, varchar, jsonb, text, varchar)
            OWNER TO ibbot_altdata_owner;

        -- The application keeps normal CRUD compatibility everywhere else.
        -- Migrations continue to run as ibbot, so grant both current objects
        -- and objects created by future migrations to ibbot_app.
        GRANT USAGE ON SCHEMA public TO ibbot_app;
        DO $do$
        DECLARE
            object_name text;
        BEGIN
            FOR object_name IN
                SELECT c.relname
                FROM pg_class AS c
                JOIN pg_namespace AS n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relkind IN ('r', 'p')
                  AND c.relname NOT IN ('altdata_snapshots', 'altdata_snapshot_corrections')
            LOOP
                EXECUTE format('GRANT ALL PRIVILEGES ON TABLE public.%I TO ibbot_app', object_name);
            END LOOP;
            FOR object_name IN
                SELECT c.relname
                FROM pg_class AS c
                JOIN pg_namespace AS n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relkind = 'S'
                  AND c.relname NOT IN ('altdata_snapshots_id_seq', 'altdata_snapshot_corrections_id_seq')
            LOOP
                EXECUTE format('GRANT ALL PRIVILEGES ON SEQUENCE public.%I TO ibbot_app', object_name);
            END LOOP;
        END;
        $do$;
        ALTER DEFAULT PRIVILEGES FOR ROLE ibbot IN SCHEMA public
            GRANT ALL PRIVILEGES ON TABLES TO ibbot_app;
        ALTER DEFAULT PRIVILEGES FOR ROLE ibbot IN SCHEMA public
            GRANT ALL PRIVILEGES ON SEQUENCES TO ibbot_app;

        -- The collector only appends.  Do not grant UPDATE or DELETE directly;
        -- the application cannot manufacture a correction ledger row either.
        REVOKE ALL ON TABLE altdata_snapshots FROM ibbot_app;
        REVOKE ALL ON TABLE altdata_snapshot_corrections FROM ibbot_app;
        REVOKE ALL ON SEQUENCE altdata_snapshots_id_seq FROM ibbot_app;
        REVOKE ALL ON SEQUENCE altdata_snapshot_corrections_id_seq FROM ibbot_app;
        GRANT SELECT, INSERT ON TABLE altdata_snapshots TO ibbot_app;
        GRANT SELECT ON TABLE altdata_snapshot_corrections TO ibbot_app;
        GRANT USAGE, SELECT ON SEQUENCE altdata_snapshots_id_seq TO ibbot_app;

        -- An application credential must not be able to manufacture an
        -- apparently-audited correction by calling the SECURITY DEFINER
        -- routine.  A separate, out-of-band privileged maintenance path is
        -- required for the exceptional correction procedure.
        REVOKE ALL ON FUNCTION apply_altdata_snapshot_correction(integer, integer, varchar, jsonb, text, varchar)
            FROM ibbot_app;
        """
    )


def downgrade() -> None:
    # Privilege separation is a one-way security hardening step.  Restoring
    # superuser/table ownership would reintroduce the trigger bypass.
    raise RuntimeError("0014_altdata_owner_separation is intentionally irreversible")
