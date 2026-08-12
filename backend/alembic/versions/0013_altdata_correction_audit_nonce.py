"""bind alt-data corrections to an audit row in the same transaction

Revision ID: 0013_altdata_correction_audit_nonce
Revises: 0012_altdata_append_only
Create Date: 2026-08-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0013_altdata_correction_audit_nonce"
down_revision = "0012_altdata_append_only"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "altdata_snapshot_corrections",
        sa.Column("correction_nonce", postgresql.UUID(as_uuid=False), nullable=True),
    )
    op.add_column(
        "altdata_snapshot_corrections",
        sa.Column("correction_txid", sa.BigInteger(), nullable=True),
    )
    # 0012 had not recorded any corrections when this hardening migration was
    # introduced.  The NOT NULL/UNIQUE constraints make a correction record a
    # one-use capability rather than a session flag an UPDATE client can forge.
    op.alter_column("altdata_snapshot_corrections", "correction_nonce", nullable=False)
    op.alter_column("altdata_snapshot_corrections", "correction_txid", nullable=False)
    op.create_unique_constraint(
        "uq_altdata_snapshot_corrections_nonce",
        "altdata_snapshot_corrections",
        ["correction_nonce"],
    )
    op.execute(
        """
        CREATE FUNCTION reject_altdata_snapshot_correction_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'altdata_snapshot_corrections is append-only'
                USING ERRCODE = 'P0001';
        END;
        $$;

        CREATE TRIGGER altdata_snapshot_corrections_reject_mutation
        BEFORE UPDATE OR DELETE ON altdata_snapshot_corrections
        FOR EACH ROW EXECUTE FUNCTION reject_altdata_snapshot_correction_mutation();

        CREATE OR REPLACE FUNCTION reject_altdata_snapshot_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            -- A session GUC is only a pointer.  It is insufficient by itself:
            -- the audit entry must bind this exact old/new mutation, snapshot,
            -- and transaction before the row can be changed.
            IF TG_OP = 'UPDATE' AND EXISTS (
                SELECT 1
                FROM altdata_snapshot_corrections AS correction
                WHERE correction.snapshot_id = NEW.id
                  AND correction.correction_txid = txid_current()
                  AND correction.correction_nonce::text = current_setting('ib_bot.altdata_authorized_correction', true)
                  AND correction.old_n_rows = OLD.n_rows
                  AND correction.old_content_hash IS NOT DISTINCT FROM OLD.content_hash
                  AND correction.old_payload IS NOT DISTINCT FROM OLD.payload
                  AND correction.new_n_rows = NEW.n_rows
                  AND correction.new_content_hash IS NOT DISTINCT FROM NEW.content_hash
                  AND correction.new_payload IS NOT DISTINCT FROM NEW.payload
            ) THEN
                RETURN NEW;
            END IF;
            RAISE EXCEPTION 'altdata_snapshots is append-only; use apply_altdata_snapshot_correction for an audited correction'
                USING ERRCODE = 'P0001';
        END;
        $$;

        CREATE OR REPLACE FUNCTION apply_altdata_snapshot_correction(
            p_snapshot_id integer,
            p_n_rows integer,
            p_content_hash varchar(64),
            p_payload jsonb,
            p_reason text,
            p_actor varchar(128)
        ) RETURNS void
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = public AS $$
        DECLARE
            old_snapshot altdata_snapshots%ROWTYPE;
            correction_nonce uuid := md5(random()::text || clock_timestamp()::text || txid_current()::text)::uuid;
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
                new_n_rows, new_content_hash, new_payload, correction_nonce, correction_txid
            ) VALUES (
                old_snapshot.id, p_actor, p_reason, old_snapshot.n_rows,
                old_snapshot.content_hash, old_snapshot.payload, p_n_rows,
                p_content_hash, p_payload, correction_nonce, txid_current()
            );
            PERFORM set_config('ib_bot.altdata_authorized_correction', correction_nonce::text, true);
            UPDATE altdata_snapshots
            SET n_rows = p_n_rows, content_hash = p_content_hash, payload = p_payload
            WHERE id = p_snapshot_id;
        END;
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS altdata_snapshot_corrections_reject_mutation ON altdata_snapshot_corrections;"
    )
    op.execute("DROP FUNCTION IF EXISTS reject_altdata_snapshot_correction_mutation();")
    op.drop_constraint(
        "uq_altdata_snapshot_corrections_nonce",
        "altdata_snapshot_corrections",
        type_="unique",
    )
    op.drop_column("altdata_snapshot_corrections", "correction_txid")
    op.drop_column("altdata_snapshot_corrections", "correction_nonce")
