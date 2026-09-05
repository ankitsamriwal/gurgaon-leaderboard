"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-05

Mirrors docs/01-database-schema.md exactly. Do not hand-edit this file to
add columns/tables — add a new migration instead, and update the spec doc
first if the schema itself is changing.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.execute(
        """
        CREATE TABLE users (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            phone           TEXT UNIQUE,
            email           TEXT UNIQUE,
            display_name    TEXT NOT NULL,
            is_verified     BOOLEAN NOT NULL DEFAULT FALSE,
            role            TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user','developer','admin')),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE projects (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name                TEXT NOT NULL,
            developer_name      TEXT NOT NULL,
            locality            TEXT NOT NULL,
            rera_number         TEXT NOT NULL,
            rera_verified       BOOLEAN NOT NULL DEFAULT FALSE,
            rera_verified_at    TIMESTAMPTZ,
            project_url         TEXT,
            submitted_by        UUID NOT NULL REFERENCES users(id),
            claimed_by          UUID REFERENCES users(id),
            status              TEXT NOT NULL DEFAULT 'pending_review'
                                  CHECK (status IN ('pending_review','live','rejected','suspended')),
            cached_total_paise  BIGINT NOT NULL DEFAULT 0,
            total_bid_count     INT NOT NULL DEFAULT 0,
            version             INT NOT NULL DEFAULT 0,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX ux_projects_rera_number ON projects(rera_number) WHERE status != 'rejected'"
    )
    op.execute("CREATE INDEX ix_projects_status_total ON projects(status, cached_total_paise DESC)")

    op.execute(
        """
        CREATE TABLE payment_intents (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id          UUID NOT NULL REFERENCES projects(id),
            user_id             UUID NOT NULL REFERENCES users(id),
            amount_paise        BIGINT NOT NULL CHECK (amount_paise > 0),
            idempotency_key     TEXT NOT NULL UNIQUE,
            razorpay_order_id   TEXT UNIQUE,
            status              TEXT NOT NULL DEFAULT 'created'
                                  CHECK (status IN ('created','order_created','pending_webhook','verified','failed','expired')),
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_intents_status ON payment_intents(status)")

    op.execute(
        """
        CREATE TABLE bids (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id          UUID NOT NULL REFERENCES projects(id),
            user_id             UUID NOT NULL REFERENCES users(id),
            payment_intent_id   UUID NOT NULL REFERENCES payment_intents(id) UNIQUE,
            razorpay_payment_id TEXT NOT NULL UNIQUE,
            amount_paise        BIGINT NOT NULL CHECK (amount_paise > 0),
            bidder_label        TEXT,
            is_mock             BOOLEAN NOT NULL DEFAULT FALSE,
            reversed            BOOLEAN NOT NULL DEFAULT FALSE,
            reversed_at         TIMESTAMPTZ,
            reversal_reason     TEXT,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_bids_project_created ON bids(project_id, created_at DESC)")
    op.execute("CREATE INDEX ix_bids_created_at ON bids(created_at DESC)")

    op.execute(
        """
        CREATE TABLE webhook_events (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            razorpay_event_id   TEXT NOT NULL UNIQUE,
            event_type          TEXT NOT NULL,
            payload             JSONB NOT NULL,
            signature_valid     BOOLEAN NOT NULL,
            processed           BOOLEAN NOT NULL DEFAULT FALSE,
            processed_at        TIMESTAMPTZ,
            received_at         TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE admin_actions (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            admin_user_id   UUID NOT NULL REFERENCES users(id),
            action_type     TEXT NOT NULL,
            target_table    TEXT NOT NULL,
            target_id       UUID NOT NULL,
            notes           TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE leadership_log (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id      UUID NOT NULL REFERENCES projects(id),
            became_leader_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            lost_leader_at   TIMESTAMPTZ
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS leadership_log")
    op.execute("DROP TABLE IF EXISTS admin_actions")
    op.execute("DROP TABLE IF EXISTS webhook_events")
    op.execute("DROP TABLE IF EXISTS bids")
    op.execute("DROP TABLE IF EXISTS payment_intents")
    op.execute("DROP TABLE IF EXISTS projects")
    op.execute("DROP TABLE IF EXISTS users")
