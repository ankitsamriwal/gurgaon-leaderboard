"""User-initiated legal/compliance actions (docs/06-legal-compliance.md):
account-level data export/delete requests. Project-level disputes live on
the projects router (POST /projects/{id}/dispute) since they're about a
listing, not the requester's own account.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import CurrentUser, get_current_user
from app.models import DataRequest

router = APIRouter(prefix="/account", tags=["account"])


class DataRequestBody(BaseModel):
    request_type: str  # "export" | "delete"


class DataRequestResponse(BaseModel):
    request_id: uuid.UUID
    status: str


@router.post("/data-request", status_code=202, response_model=DataRequestResponse)
async def create_data_request(
    body: DataRequestBody,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
):
    """docs/06: "Build a data export/delete flow for user accounts (even a
    manual admin-actioned process is acceptable for v1, but the
    capability must exist)." This files the request; an admin fulfills it
    (app/routers/admin.py) — export is compiled and sent out of band,
    delete anonymizes the account while retaining ledger/payment records
    per docs/06's retention requirement.
    """
    if body.request_type not in ("export", "delete"):
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "INVALID_REQUEST", "message": "request_type must be 'export' or 'delete'"}},
        )

    request = DataRequest(user_id=uuid.UUID(user.id), request_type=body.request_type, status="pending")
    db.add(request)
    await db.commit()
    await db.refresh(request)
    return DataRequestResponse(request_id=request.id, status=request.status)


class MyBid(BaseModel):
    bid_id: uuid.UUID
    project_id: uuid.UUID
    project_name: str
    amount_paise: int
    reversed: bool
    created_at: datetime


class MyProject(BaseModel):
    project_id: uuid.UUID
    name: str
    developer_name: str
    locality: str
    status: str
    total_paise: int
    bid_count: int


class AccountMeResponse(BaseModel):
    bids: list[MyBid]
    projects: list[MyProject]


@router.get("/me", response_model=AccountMeResponse)
async def account_me(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
):
    """The caller's own bid history and project submissions, newest first.

    Backs the dashboard. Read-only; no admin involvement.
    """
    from sqlalchemy import select

    from app.models import Bid, Project

    bid_rows = (
        await db.execute(
            select(Bid, Project.name)
            .join(Project, Bid.project_id == Project.id)
            .where(Bid.user_id == uuid.UUID(user.id))
            .order_by(Bid.created_at.desc())
            .limit(50)
        )
    ).all()

    project_rows = (
        await db.execute(
            select(Project)
            .where(Project.submitted_by == uuid.UUID(user.id))
            .order_by(Project.created_at.desc())
            .limit(50)
        )
    ).scalars().all()

    return AccountMeResponse(
        bids=[
            MyBid(
                bid_id=b.id,
                project_id=b.project_id,
                project_name=name,
                amount_paise=b.amount_paise,
                reversed=b.reversed,
                created_at=b.created_at,
            )
            for b, name in bid_rows
        ],
        projects=[
            MyProject(
                project_id=pr.id,
                name=pr.name,
                developer_name=pr.developer_name,
                locality=pr.locality,
                status=pr.status,
                total_paise=pr.cached_total_paise,
                bid_count=pr.total_bid_count,
            )
            for pr in project_rows
        ],
    )
