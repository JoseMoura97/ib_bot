"""separate PIT archive ownership from the application database role

Revision ID: 0014_altdata_owner_separation
Revises: 0013_altdata_correction_audit_nonce
Create Date: 2026-08-12

The application role used to be the database/table owner and a PostgreSQL
superuser.  That role could suppress row triggers with
``session_replication_role``.  The protected archive is now owned by a no-login
role while the application keeps only its required data privileges.
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

        ALTER TABLE altdata_snapshots OWNER TO ibbot_altdata_owner;
        ALTER TABLE altdata_snapshot_corrections OWNER TO ibbot_altdata_owner;
        ALTER SEQUENCE altdata_snapshots_id_seq OWNER TO ibbot_altdata_owner;
        ALTER SEQUENCE altdata_snapshot_corrections_id_seq OWNER TO ibbot_altdata_owner;
        ALTER FUNCTION reject_altdata_snapshot_mutation() OWNER TO ibbot_altdata_owner;
        ALTER FUNCTION reject_altdata_snapshot_correction_mutation() OWNER TO ibbot_altdata_owner;
        ALTER FUNCTION apply_altdata_snapshot_correction(integer, integer, varchar, jsonb, text, varchar)
            OWNER TO ibbot_altdata_owner;

        -- ``public`` is owned by pg_database_owner; moving database ownership
        -- removes ibbot's implicit CREATE privilege there as well.
        ALTER DATABASE ibbot OWNER TO ibbot_altdata_owner;

        REVOKE ALL ON TABLE altdata_snapshots FROM ibbot;
        REVOKE ALL ON TABLE altdata_snapshot_corrections FROM ibbot;
        REVOKE ALL ON SEQUENCE altdata_snapshots_id_seq FROM ibbot;
        REVOKE ALL ON SEQUENCE altdata_snapshot_corrections_id_seq FROM ibbot;
        -- The collector only appends.  Do not grant UPDATE or DELETE directly:
        -- even though the trigger rejects them, withholding the privilege
        -- makes the boundary independent of trigger state.
        GRANT SELECT, INSERT ON TABLE altdata_snapshots TO ibbot;
        GRANT SELECT ON TABLE altdata_snapshot_corrections TO ibbot;
        GRANT USAGE, SELECT ON SEQUENCE altdata_snapshots_id_seq TO ibbot;

        -- An application credential must not be able to manufacture an
        -- apparently-audited correction by calling the SECURITY DEFINER
        -- routine.  A separate, out-of-band privileged maintenance path is
        -- required for the exceptional correction procedure.
        REVOKE ALL ON FUNCTION apply_altdata_snapshot_correction(integer, integer, varchar, jsonb, text, varchar)
            FROM ibbot;

        ALTER ROLE ibbot NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
        """
    )


def downgrade() -> None:
    # Privilege separation is a one-way security hardening step.  Restoring
    # superuser/table ownership would reintroduce the trigger bypass.
    raise RuntimeError("0014_altdata_owner_separation is intentionally irreversible")
