"""User-initiated legal/compliance actions (docs/06-legal-compliance.md):
account-level data export/delete requests. Project-level disputes live on
the projects router (POST /projects/{id}/dispute) since they're about a
listing, not the requester's own account.
"""

import uuid
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
