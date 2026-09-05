"""project_claims: developer ownership claim queue (docs/02, docs/04)

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-05

Not in docs/01-database-schema.md. docs/02-api-spec.md's
POST /projects/{id}/claim needs somewhere to queue a claim for admin
review before projects.claimed_by is set.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE project_claims (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id          UUID NOT NULL REFERENCES projects(id),
            claimant_user_id    UUID NOT NULL REFERENCES users(id),
            document_url        TEXT,
            status              TEXT NOT NULL DEFAULT 'pending'
                                  CHECK (status IN ('pending','approved','rejected')),
            reviewed_by         UUID REFERENCES users(id),
            reviewed_at         TIMESTAMPTZ,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_project_claims_status ON project_claims(status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS project_claims")
