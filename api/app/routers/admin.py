import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import CurrentUser, require_role
from app.models import AdminAction, Bid, Project, ProjectClaim, ReconciliationReport, User
from app.redis_client import redis_client
from app.services.anti_fraud import compute_anti_fraud_flags
from app.services.bids import reverse_bid
from app.services.projects import LEADERBOARD_CACHE_KEY, publish_leaderboard_update
from app.services.reconciliation import run_reconciliation

router = APIRouter(prefix="/admin", tags=["admin"])
require_admin = require_role("admin")


def _log_action(session: AsyncSession, *, admin_id: uuid.UUID, action_type: str, target_table: str, target_id: uuid.UUID, notes: str | None = None) -> None:
    session.add(
        AdminAction(
            admin_user_id=admin_id,
            action_type=action_type,
            target_table=target_table,
            target_id=target_id,
            notes=notes,
        )
    )


@router.get("/projects/pending")
async def list_pending_projects(
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[CurrentUser, Depends(require_admin)],
):
    projects = (
        await db.execute(select(Project).where(Project.status == "pending_review").order_by(Project.created_at.asc()))
    ).scalars().all()
    return {
        "projects": [
            {
                "id": str(p.id),
                "name": p.name,
                "developer_name": p.developer_name,
                "locality": p.locality,
                "rera_number": p.rera_number,
                "rera_verified": p.rera_verified,
                "submitted_by": str(p.submitted_by),
                "created_at": p.created_at.isoformat(),
                # doc02: "RERA lookup helper links" — Haryana RERA's public
                # search has no documented deep-link-by-number API, so this
                # points admins at the search portal itself to look it up.
                "rera_lookup_url": "https://haryanarera.gov.in/",
            }
            for p in projects
        ]
    }


@router.post("/projects/{project_id}/approve")
async def approve_project(
    project_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[CurrentUser, Depends(require_admin)],
):
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "unknown project"}})

    project.status = "live"
    project.updated_at = datetime.now(timezone.utc)
    _log_action(db, admin_id=uuid.UUID(admin.id), action_type="approve_project", target_table="projects", target_id=project_id)
    await db.commit()
    # Moderation actions should be visible immediately, not wait out the
    # leaderboard's 5-10s read cache (docs/02).
    await redis_client.delete(LEADERBOARD_CACHE_KEY)
    return {"id": str(project.id), "status": project.status}


class RejectBody(BaseModel):
    reason: str


@router.post("/projects/{project_id}/reject")
async def reject_project(
    project_id: uuid.UUID,
    body: RejectBody,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[CurrentUser, Depends(require_admin)],
):
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "unknown project"}})

    project.status = "rejected"
    project.updated_at = datetime.now(timezone.utc)
    _log_action(
        db, admin_id=uuid.UUID(admin.id), action_type="reject_project", target_table="projects",
        target_id=project_id, notes=body.reason,
    )
    await db.commit()
    await redis_client.delete(LEADERBOARD_CACHE_KEY)
    return {"id": str(project.id), "status": project.status}


@router.post("/projects/{project_id}/verify-rera")
async def verify_rera(
    project_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[CurrentUser, Depends(require_admin)],
):
    """Marks rera_verified=true after manual check against the Haryana RERA
    public portal (docs/02, docs/05) — never automated."""
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "unknown project"}})

    project.rera_verified = True
    project.rera_verified_at = datetime.now(timezone.utc)
    _log_action(db, admin_id=uuid.UUID(admin.id), action_type="verify_rera", target_table="projects", target_id=project_id)
    await db.commit()
    return {"id": str(project.id), "rera_verified": project.rera_verified}


@router.get("/claims/pending")
async def list_pending_claims(
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[CurrentUser, Depends(require_admin)],
):
    claims = (
        await db.execute(select(ProjectClaim).where(ProjectClaim.status == "pending").order_by(ProjectClaim.created_at.asc()))
    ).scalars().all()
    return {
        "claims": [
            {
                "id": str(c.id),
                "project_id": str(c.project_id),
                "claimant_user_id": str(c.claimant_user_id),
                "document_url": c.document_url,
                "created_at": c.created_at.isoformat(),
            }
            for c in claims
        ]
    }


@router.post("/claims/{claim_id}/approve")
async def approve_claim(
    claim_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[CurrentUser, Depends(require_admin)],
):
    claim = await db.get(ProjectClaim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "unknown claim"}})

    project = await db.get(Project, claim.project_id)
    claimant = await db.get(User, claim.claimant_user_id)

    claim.status = "approved"
    claim.reviewed_by = uuid.UUID(admin.id)
    claim.reviewed_at = datetime.now(timezone.utc)
    project.claimed_by = claimant.id
    claimant.role = "developer"

    _log_action(db, admin_id=uuid.UUID(admin.id), action_type="approve_claim", target_table="project_claims", target_id=claim_id)
    await db.commit()
    return {"id": str(claim.id), "status": claim.status}


class RejectClaimBody(BaseModel):
    reason: str | None = None


@router.post("/claims/{claim_id}/reject")
async def reject_claim(
    claim_id: uuid.UUID,
    body: RejectClaimBody,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[CurrentUser, Depends(require_admin)],
):
    claim = await db.get(ProjectClaim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "unknown claim"}})

    claim.status = "rejected"
    claim.reviewed_by = uuid.UUID(admin.id)
    claim.reviewed_at = datetime.now(timezone.utc)

    _log_action(
        db, admin_id=uuid.UUID(admin.id), action_type="reject_claim", target_table="project_claims",
        target_id=claim_id, notes=body.reason,
    )
    await db.commit()
    return {"id": str(claim.id), "status": claim.status}


@router.post("/bids/{bid_id}/reverse")
async def reverse_bid_endpoint(
    bid_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[CurrentUser, Depends(require_admin)],
):
    """Refund/chargeback handling (docs/02, docs/03)."""
    bid = await db.get(Bid, bid_id)
    if bid is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "unknown bid"}})

    await reverse_bid(db, bid_id=bid_id, reason="admin reversal")
    _log_action(db, admin_id=uuid.UUID(admin.id), action_type="refund_bid", target_table="bids", target_id=bid_id)
    await db.commit()
    await publish_leaderboard_update(db)
    await redis_client.delete(LEADERBOARD_CACHE_KEY)

    updated = await db.get(Bid, bid_id)
    return {"id": str(updated.id), "reversed": updated.reversed}


@router.get("/reconciliation/report")
async def latest_reconciliation_report(
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[CurrentUser, Depends(require_admin)],
):
    """Returns the latest nightly reconciliation job output (docs/02, docs/03)."""
    report = (
        await db.execute(select(ReconciliationReport).order_by(ReconciliationReport.run_at.desc()).limit(1))
    ).scalar_one_or_none()
    if report is None:
        return {"report": None}
    return {
        "report": {
            "id": str(report.id),
            "run_at": report.run_at.isoformat(),
            "projects_checked": report.projects_checked,
            "mismatch_count": report.mismatch_count,
            "mismatches": report.mismatches,
        }
    }


@router.post("/reconciliation/run")
async def trigger_reconciliation(
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[CurrentUser, Depends(require_admin)],
):
    """Runs the reconciliation job on demand. The real schedule is an
    external nightly cron/APScheduler job calling the same
    run_reconciliation() (docs/03: 2 AM IST) — see api/scripts/run_reconciliation.py.
    This on-demand trigger is not in docs/02 but is the minimal way to
    make the job operable/testable without standing up a scheduler.
    """
    report = await run_reconciliation(db)
    return {"report": report}


@router.get("/anti-fraud/flags")
async def anti_fraud_flags(
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[CurrentUser, Depends(require_admin)],
):
    """Wash-trading heuristics for admin review (docs/05) — flags, never
    auto-blocks."""
    return await compute_anti_fraud_flags(db)
