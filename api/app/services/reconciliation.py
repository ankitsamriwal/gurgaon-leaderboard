"""Nightly reconciliation job (docs/03-payment-integration.md).

docs/03 also calls for cross-checking against Razorpay's settlement
report/payments API — skipped here since no real Razorpay account exists
for this build (see the top-level README's known-gap notes). What's
implemented is the part that doesn't need Razorpay and is this build's
actual release gate (docs/07 Phase 6): recompute every project's total
from the ledger and diff against cached_total_paise, exactly as
docs/01-database-schema.md's "Rebuild/repair" query prescribes.
"""

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Bid, Project, ReconciliationReport

logger = logging.getLogger("reconciliation")


async def run_reconciliation(session: AsyncSession) -> dict:
    rows = (
        await session.execute(
            select(
                Project.id,
                Project.cached_total_paise,
                Project.total_bid_count,
                func.coalesce(func.sum(Bid.amount_paise).filter(Bid.reversed.is_(False)), 0).label("ledger_total"),
                func.count(Bid.id).filter(Bid.reversed.is_(False)).label("ledger_count"),
            )
            .outerjoin(Bid, Bid.project_id == Project.id)
            .group_by(Project.id)
        )
    ).all()

    mismatches = []
    for row in rows:
        ledger_total = int(row.ledger_total)
        ledger_count = int(row.ledger_count)
        if ledger_total != row.cached_total_paise or ledger_count != row.total_bid_count:
            mismatches.append(
                {
                    "project_id": str(row.id),
                    "cached_total_paise": row.cached_total_paise,
                    "ledger_total_paise": ledger_total,
                    "cached_bid_count": row.total_bid_count,
                    "ledger_bid_count": ledger_count,
                }
            )

    # Alert (log) BEFORE correcting — docs/03: "auto-correct the cache only
    # after the alert fires, never silently." This report row *is* the
    # alert's paper trail; logging at ERROR is the fire-a-page-someone hook
    # a real deployment would wire to Slack/PagerDuty.
    for m in mismatches:
        logger.error(
            "reconciliation mismatch: project=%s cached_total=%s ledger_total=%s cached_count=%s ledger_count=%s",
            m["project_id"],
            m["cached_total_paise"],
            m["ledger_total_paise"],
            m["cached_bid_count"],
            m["ledger_bid_count"],
        )

    for m in mismatches:
        project = await session.get(Project, uuid.UUID(m["project_id"]))
        project.cached_total_paise = m["ledger_total_paise"]
        project.total_bid_count = m["ledger_bid_count"]
        m["corrected"] = True

    report = ReconciliationReport(
        projects_checked=len(rows),
        mismatch_count=len(mismatches),
        mismatches=mismatches,
    )
    session.add(report)
    await session.commit()
    await session.refresh(report)

    return {
        "id": str(report.id),
        "run_at": report.run_at.isoformat(),
        "projects_checked": report.projects_checked,
        "mismatch_count": report.mismatch_count,
        "mismatches": report.mismatches,
    }
