"""project_disputes, data_requests (docs/06-legal-compliance.md)

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-05

Not in docs/01-database-schema.md. docs/06 calls for a takedown/dispute
fast path (point 4) and a DPDP-compliant data export/delete capability
(the Data protection section) — neither table exists yet.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE project_disputes (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id          UUID NOT NULL REFERENCES projects(id),
            filed_by_user_id    UUID NOT NULL REFERENCES users(id),
            reason              TEXT NOT NULL,
            contact_email       TEXT,
            status              TEXT NOT NULL DEFAULT 'pending'
                                  CHECK (status IN ('pending','resolved','rejected')),
            priority            BOOLEAN NOT NULL DEFAULT TRUE,
            resolved_by         UUID REFERENCES users(id),
            resolved_at         TIMESTAMPTZ,
            resolution_notes    TEXT,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_project_disputes_status ON project_disputes(status)")

    op.execute(
        """
        CREATE TABLE data_requests (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id         UUID NOT NULL REFERENCES users(id),
            request_type    TEXT NOT NULL CHECK (request_type IN ('export','delete')),
            status          TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','fulfilled')),
            fulfilled_by    UUID REFERENCES users(id),
            fulfilled_at    TIMESTAMPTZ,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_data_requests_status ON data_requests(status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS data_requests")
    op.execute("DROP TABLE IF EXISTS project_disputes")
