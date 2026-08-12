"""make alt-data snapshots append-only with an audited correction path

Revision ID: 0012_altdata_append_only
Revises: 0011_altdata_snapshots
Create Date: 2026-08-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0012_altdata_append_only"
down_revision = "0011_altdata_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "altdata_snapshot_corrections",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("corrected_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("old_n_rows", sa.Integer(), nullable=False),
        sa.Column("old_content_hash", sa.String(length=64), nullable=True),
        sa.Column("old_payload", postgresql.JSONB(), nullable=True),
        sa.Column("new_n_rows", sa.Integer(), nullable=False),
        sa.Column("new_content_hash", sa.String(length=64), nullable=True),
        sa.Column("new_payload", postgresql.JSONB(), nullable=True),
    )
    op.create_index(
        "ix_altdata_snapshot_corrections_snapshot_id",
        "altdata_snapshot_corrections",
        ["snapshot_id"],
    )
    op.execute(
        """
        CREATE FUNCTION reject_altdata_snapshot_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'UPDATE'
               AND current_setting('ib_bot.altdata_authorized_correction', true) = 'active'
            THEN
                RETURN NEW;
            END IF;
            RAISE EXCEPTION 'altdata_snapshots is append-only; use apply_altdata_snapshot_correction for an audited correction'
                USING ERRCODE = 'P0001';
        END;
        $$;

        CREATE TRIGGER altdata_snapshots_reject_mutation
        BEFORE UPDATE OR DELETE ON altdata_snapshots
        FOR EACH ROW EXECUTE FUNCTION reject_altdata_snapshot_mutation();

        CREATE FUNCTION apply_altdata_snapshot_correction(
            p_snapshot_id integer,
            p_n_rows integer,
            p_content_hash varchar(64),
            p_payload jsonb,
            p_reason text,
            p_actor varchar(128)
        ) RETURNS void
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = public AS $$
        DECLARE old_snapshot altdata_snapshots%ROWTYPE;
        BEGIN
            IF coalesce(btrim(p_reason), '') = '' OR coalesce(btrim(p_actor), '') = '' THEN
                RAISE EXCEPTION 'audited correction requires a non-empty actor and reason';
            END IF;
            SELECT * INTO old_snapshot FROM altdata_snapshots WHERE id = p_snapshot_id FOR UPDATE;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'altdata snapshot % does not exist', p_snapshot_id;
            END IF;
            INSERT INTO altdata_snapshot_corrections (
                snapshot_id, actor, reason, old_n_rows, old_content_hash, old_payload,
                new_n_rows, new_content_hash, new_payload
            ) VALUES (
                old_snapshot.id, p_actor, p_reason, old_snapshot.n_rows,
                old_snapshot.content_hash, old_snapshot.payload, p_n_rows,
                p_content_hash, p_payload
            );
            PERFORM set_config('ib_bot.altdata_authorized_correction', 'active', true);
            UPDATE altdata_snapshots
            SET n_rows = p_n_rows, content_hash = p_content_hash, payload = p_payload
            WHERE id = p_snapshot_id;
        END;
        $$;

        REVOKE ALL ON FUNCTION apply_altdata_snapshot_correction(integer, integer, varchar, jsonb, text, varchar) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION apply_altdata_snapshot_correction(integer, integer, varchar, jsonb, text, varchar) TO ibbot;
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP FUNCTION IF EXISTS apply_altdata_snapshot_correction(integer, integer, varchar, jsonb, text, varchar);"
    )
    op.execute("DROP TRIGGER IF EXISTS altdata_snapshots_reject_mutation ON altdata_snapshots;")
    op.execute("DROP FUNCTION IF EXISTS reject_altdata_snapshot_mutation();")
    op.drop_index("ix_altdata_snapshot_corrections_snapshot_id", table_name="altdata_snapshot_corrections")
    op.drop_table("altdata_snapshot_corrections")
