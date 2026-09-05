"""Internal, non-production-only test endpoints.

Phase 1 (docs/07-implementation-plan.md) needs to load-test the bid
acceptance transaction "before wiring up Razorpay at all". These endpoints
stand in for what Phase 3's real webhook handler will do — they must never
be registered in production. app/main.py only includes this router when
`settings.environment != "production"`, checked once at app-factory time,
not per-request (see docs/03-payment-integration.md's mock-mode guidance).

Bids created here are flagged `is_mock=True` and projects are seeded
directly into `status='live'`, skipping the admin moderation gate in
docs/01-database-schema.md — both are fine only because this router does
not exist in a production build.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import User, Project
from app.services.bids import accept_bid

router = APIRouter(prefix="/internal/test", tags=["internal-test"])


class SeedProjectRequest(BaseModel):
    rera_number: str
    name: str = "Test Project"
    developer_name: str = "Test Developer"
    locality: str = "Sector 1"


class SeedProjectResponse(BaseModel):
    project_id: uuid.UUID
    submitter_user_id: uuid.UUID


@router.post("/seed-project", response_model=SeedProjectResponse)
async def seed_project(body: SeedProjectRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    submitter = User(display_name="Test Submitter", email=f"submitter-{uuid.uuid4()}@example.test")
    db.add(submitter)
    await db.flush()

    project = Project(
        name=body.name,
        developer_name=body.developer_name,
        locality=body.locality,
        rera_number=body.rera_number,
        submitted_by=submitter.id,
        status="live",
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return SeedProjectResponse(project_id=project.id, submitter_user_id=submitter.id)


class SeedUserResponse(BaseModel):
    user_id: uuid.UUID


@router.post("/seed-user", response_model=SeedUserResponse)
async def seed_user(db: Annotated[AsyncSession, Depends(get_db)]):
    user = User(display_name="Test Bidder", email=f"bidder-{uuid.uuid4()}@example.test")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return SeedUserResponse(user_id=user.id)


class SettleBidRequest(BaseModel):
    project_id: uuid.UUID
    user_id: uuid.UUID
    amount_paise: int
    idempotency_key: str


class SettleBidResponse(BaseModel):
    bid_id: uuid.UUID
    project_id: uuid.UUID
    cached_total_paise: int
    total_bid_count: int
    already_settled: bool


@router.post("/settle", response_model=SettleBidResponse)
async def settle_bid(body: SettleBidRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    """Stand-in for the Razorpay webhook handler (docs/03-payment-integration.md).

    Gets-or-creates a payment_intent by idempotency_key (mirrors
    POST /payments/intent's dedup rule) and settles it, through the same
    accept_bid() transaction the real webhook will call.
    """
    if body.amount_paise <= 0:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "AMOUNT_TOO_LOW", "message": "amount_paise must be positive"}},
        )

    result = await accept_bid(
        db,
        project_id=body.project_id,
        user_id=body.user_id,
        amount_paise=body.amount_paise,
        idempotency_key=body.idempotency_key,
        razorpay_payment_id_for=lambda intent: f"mock_{intent.id}",
        bidder_label="mock",
        is_mock=True,
    )

    return SettleBidResponse(
        bid_id=result.bid.id,
        project_id=result.project.id,
        cached_total_paise=result.project.cached_total_paise,
        total_bid_count=result.project.total_bid_count,
        already_settled=result.already_settled,
    )
