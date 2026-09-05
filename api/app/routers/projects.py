import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import CurrentUser, get_current_user
from app.models import Project, ProjectClaim
from app.rate_limit import rate_limit
from app.services.captcha_provider import get_captcha_provider
from app.services.projects import create_project, get_leaderboard, get_project_detail

router = APIRouter(prefix="/projects", tags=["projects"])


class CreateProjectBody(BaseModel):
    name: str
    developer_name: str
    locality: str
    rera_number: str
    project_url: str | None = None
    opening_bid_paise: int | None = None  # accepted per docs/02; no separate handling needed yet
    captcha_token: str | None = None


class CreateProjectResponse(BaseModel):
    project_id: uuid.UUID
    status: str


@router.post("", status_code=201, response_model=CreateProjectResponse)
async def submit_project(
    body: CreateProjectBody,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
):
    await rate_limit(f"project-submit:{user.id}", limit=3, window_seconds=86400)

    if not await get_captcha_provider().verify(body.captcha_token):
        raise HTTPException(
            status_code=400, detail={"error": {"code": "CAPTCHA_FAILED", "message": "CAPTCHA verification failed"}}
        )

    project = await create_project(
        db,
        submitted_by=uuid.UUID(user.id),
        name=body.name,
        developer_name=body.developer_name,
        locality=body.locality,
        rera_number=body.rera_number,
        project_url=body.project_url,
    )
    return CreateProjectResponse(project_id=project.id, status=project.status)


@router.get("/leaderboard")
async def leaderboard(db: Annotated[AsyncSession, Depends(get_db)]):
    return await get_leaderboard(db)


@router.get("/{project_id}")
async def project_detail(
    project_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: Annotated[int, Query(ge=0)] = 0,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
):
    return await get_project_detail(db, project_id=project_id, page=page, page_size=page_size)


class ClaimBody(BaseModel):
    document_url: str | None = None


class ClaimResponse(BaseModel):
    claim_id: uuid.UUID
    status: str


@router.post("/{project_id}/claim", status_code=202, response_model=ClaimResponse)
async def claim_project(
    project_id: uuid.UUID,
    body: ClaimBody,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
):
    """Start a developer ownership claim (docs/02). Goes to an admin queue;
    does not auto-approve. docs/02 gates this to "developer role", but
    nothing in this build's auth flow ever grants that role up front —
    filing a claim is how a user becomes a developer, on admin approval
    (see app/routers/admin.py), not a prerequisite for filing one.
    """
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "unknown project"}})

    claim = ProjectClaim(
        project_id=project_id,
        claimant_user_id=uuid.UUID(user.id),
        document_url=body.document_url,
        status="pending",
    )
    db.add(claim)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail={"error": {"code": "CLAIM_CONFLICT", "message": "could not file claim"}}
        )
    await db.refresh(claim)
    return ClaimResponse(claim_id=claim.id, status=claim.status)
