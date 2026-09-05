"""auth tables: otp_requests, refresh_tokens

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-05

Not in docs/01-database-schema.md (which only covers the money tables) —
added here to support docs/00-overview.md's "OTP + JWT sessions, refresh
rotation with reuse detection" auth design from docs/05-security-anti-fraud.md.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE otp_requests (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            phone           TEXT,
            email           TEXT,
            otp_hash        TEXT NOT NULL,
            attempts        INT NOT NULL DEFAULT 0,
            consumed        BOOLEAN NOT NULL DEFAULT FALSE,
            expires_at      TIMESTAMPTZ NOT NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            CHECK (phone IS NOT NULL OR email IS NOT NULL)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE refresh_tokens (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id         UUID NOT NULL REFERENCES users(id),
            family_id       UUID NOT NULL,
            token_hash      TEXT NOT NULL UNIQUE,
            revoked         BOOLEAN NOT NULL DEFAULT FALSE,
            replaced_by     UUID REFERENCES refresh_tokens(id),
            expires_at      TIMESTAMPTZ NOT NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_refresh_tokens_family ON refresh_tokens(family_id)")
    op.execute("CREATE INDEX ix_refresh_tokens_user ON refresh_tokens(user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS refresh_tokens")
    op.execute("DROP TABLE IF EXISTS otp_requests")
