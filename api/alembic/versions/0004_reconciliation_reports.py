"""reconciliation_reports (docs/03, docs/07 Phase 6)

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-05

Not in docs/01-database-schema.md. Stores each nightly reconciliation
run's mismatch findings so GET /admin/reconciliation/report (docs/02) has
something to return, and so "auto-correct the cache only after the alert
fires, never silently" (docs/03) leaves a paper trail.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE reconciliation_reports (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
            projects_checked    INT NOT NULL,
            mismatch_count      INT NOT NULL,
            mismatches          JSONB NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX ix_reconciliation_reports_run_at ON reconciliation_reports(run_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS reconciliation_reports")
