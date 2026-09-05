import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.deps import CurrentUser, get_current_user
from app.models import PaymentIntent, Project
from app.rate_limit import rate_limit
from app.services.bids import accept_bid
from app.services.projects import publish_leaderboard_update
from app.services.razorpay_client import RazorpayClient, get_razorpay_client

router = APIRouter(prefix="/payments", tags=["payments"])


class PaymentsConfigResponse(BaseModel):
    razorpay_key_id: str


@router.get("/config", response_model=PaymentsConfigResponse)
async def payments_config():
    """Lets the frontend decide, before calling anything, whether real
    Razorpay Checkout is available or it should fall back to the demo
    /payments/mock path — rather than discovering that by provoking a
    failure out of /payments/intent. Key ID is safe to expose (docs/03).
    """
    return PaymentsConfigResponse(razorpay_key_id=settings.razorpay_key_id)


class CreateIntentBody(BaseModel):
    project_id: uuid.UUID
    amount_paise: int
    idempotency_key: str


class CreateIntentResponse(BaseModel):
    intent_id: uuid.UUID
    razorpay_order_id: str
    amount_paise: int
    razorpay_key_id: str


def _intent_response(intent: PaymentIntent) -> CreateIntentResponse:
    return CreateIntentResponse(
        intent_id=intent.id,
        razorpay_order_id=intent.razorpay_order_id,
        amount_paise=intent.amount_paise,
        razorpay_key_id=settings.razorpay_key_id,
    )


@router.post("/intent", status_code=201, response_model=CreateIntentResponse)
async def create_payment_intent(
    body: CreateIntentBody,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    razorpay: Annotated[RazorpayClient, Depends(get_razorpay_client)],
):
    """Client calls this first, before showing Razorpay Checkout (docs/02)."""
    await rate_limit(f"payments-intent-user:{user.id}", limit=20, window_seconds=3600)
    client_ip = request.client.host if request.client else "unknown"
    await rate_limit(f"payments-intent-ip:{client_ip}", limit=50, window_seconds=3600)

    if body.amount_paise <= 0:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "AMOUNT_TOO_LOW", "message": "amount_paise must be positive"}},
        )

    existing = (
        await db.execute(select(PaymentIntent).where(PaymentIntent.idempotency_key == body.idempotency_key))
    ).scalar_one_or_none()
    if existing is not None:
        return _intent_response(existing)

    project = await db.get(Project, body.project_id)
    if project is None or project.status != "live":
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "PROJECT_NOT_LIVE", "message": "project is not live"}},
        )

    order = await razorpay.create_order(amount_paise=body.amount_paise, receipt=body.idempotency_key)

    intent = PaymentIntent(
        project_id=body.project_id,
        user_id=uuid.UUID(user.id),
        amount_paise=body.amount_paise,
        idempotency_key=body.idempotency_key,
        razorpay_order_id=order["id"],
        status="order_created",
    )
    db.add(intent)
    try:
        await db.commit()
    except IntegrityError:
        # Two requests with the same idempotency_key raced past the read
        # above — the unique constraint is the backstop (docs/03).
        await db.rollback()
        existing = (
            await db.execute(select(PaymentIntent).where(PaymentIntent.idempotency_key == body.idempotency_key))
        ).scalar_one()
        return _intent_response(existing)

    await db.refresh(intent)
    return _intent_response(intent)


mock_router = APIRouter(prefix="/payments", tags=["payments-mock"])


class MockPaymentBody(BaseModel):
    project_id: uuid.UUID
    amount_paise: int
    idempotency_key: str


class MockPaymentResponse(BaseModel):
    bid_id: uuid.UUID
    already_settled: bool


@mock_router.post("/mock", response_model=MockPaymentResponse)
async def mock_payment(
    body: MockPaymentBody,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
):
    """Simulates a successful payment without Razorpay, for demos
    (docs/02-api-spec.md). Non-prod only — see app/main.py, which registers
    mock_router only when settings.is_production is False, checked once at
    app-factory time rather than per-request (docs/03's mock-mode guidance).

    Deliberately does NOT go through /payments/intent first: that endpoint
    hard-requires real Razorpay credentials (get_razorpay_client() refuses
    to run without them), which would make the demo path itself
    unreachable in any environment that doesn't have Razorpay configured —
    the exact environment this endpoint exists for. It gets-or-creates its
    own payment_intent via accept_bid(), same as the real webhook does.
    """
    if body.amount_paise <= 0:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "AMOUNT_TOO_LOW", "message": "amount_paise must be positive"}},
        )

    project = await db.get(Project, body.project_id)
    if project is None or project.status != "live":
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "PROJECT_NOT_LIVE", "message": "project is not live"}},
        )

    result = await accept_bid(
        db,
        project_id=body.project_id,
        user_id=uuid.UUID(user.id),
        amount_paise=body.amount_paise,
        idempotency_key=body.idempotency_key,
        razorpay_payment_id_for=lambda i: f"mock_{i.id}",
        is_mock=True,
    )
    if not result.already_settled:
        await publish_leaderboard_update(db)
    return MockPaymentResponse(bid_id=result.bid.id, already_settled=result.already_settled)
