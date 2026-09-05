"""The Razorpay webhook (docs/03-payment-integration.md). No user auth —
authenticated via signature instead. This is the only code path that ever
calls accept_bid() with is_mock=False; client-side checkout success is
never trusted for ranking.
"""

import hashlib
import hmac
import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.models import PaymentIntent, WebhookEvent
from app.services.bids import accept_bid

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger("webhooks")


def verify_webhook_signature(raw_body: bytes, signature: str, webhook_secret: str) -> bool:
    """Reference implementation from docs/03: HMAC-SHA256 over the raw
    request body bytes — never over a re-serialized/parsed copy."""
    expected = hmac.new(webhook_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/razorpay", status_code=200)
async def razorpay_webhook(request: Request, db: Annotated[AsyncSession, Depends(get_db)]):
    raw_body = await request.body()
    signature = request.headers.get("x-razorpay-signature", "")
    signature_valid = verify_webhook_signature(raw_body, signature, settings.razorpay_webhook_secret)

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=400, detail={"error": {"code": "INVALID_PAYLOAD", "message": "malformed JSON body"}}
        )

    event_type = payload.get("event", "unknown")
    payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
    razorpay_payment_id = payment_entity.get("id")
    # Razorpay's newer webhook deliveries carry X-Razorpay-Event-Id; fall
    # back to a deterministic key from the payload for older/test payloads.
    razorpay_event_id = request.headers.get("x-razorpay-event-id") or f"{event_type}:{razorpay_payment_id}"

    event = (
        await db.execute(select(WebhookEvent).where(WebhookEvent.razorpay_event_id == razorpay_event_id))
    ).scalar_one_or_none()

    if event is None:
        event = WebhookEvent(
            razorpay_event_id=razorpay_event_id,
            event_type=event_type,
            payload=payload,
            signature_valid=signature_valid,
        )
        db.add(event)
        # Log every delivery — valid or not — for audit, per docs/03 step (c),
        # before deciding whether to reject it.
        await db.commit()

    if not signature_valid:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "INVALID_SIGNATURE", "message": "signature verification failed"}},
        )

    if event.processed:
        # Razorpay's documented at-least-once delivery — this is expected,
        # not an error (docs/03 step d).
        return {"status": "already_processed"}

    if event_type != "payment.captured":
        event.processed = True
        await db.commit()
        return {"status": "ignored", "event": event_type}

    order_id = payment_entity.get("order_id")
    amount = payment_entity.get("amount")

    intent = (
        await db.execute(select(PaymentIntent).where(PaymentIntent.razorpay_order_id == order_id))
    ).scalar_one_or_none()

    if intent is None:
        logger.error("webhook payment.captured for unknown order_id=%s payment_id=%s", order_id, razorpay_payment_id)
        event.processed = True
        await db.commit()
        return {"status": "unmatched_order"}

    if amount != intent.amount_paise:
        # docs/03: "Mismatch → flag to admin_actions, do not insert a bid,
        # alert." admin_actions.admin_user_id is NOT NULL (docs/01) — it
        # models actions an admin *took*, not system-detected anomalies, so
        # there's no admin actor to attribute this to. Logging loudly here
        # is the stand-in; a dedicated alerts table (or a nullable
        # admin_user_id) is the real fix and is out of scope for this pass.
        logger.error(
            "webhook amount mismatch: order_id=%s expected_paise=%s got=%s",
            order_id,
            intent.amount_paise,
            amount,
        )
        event.processed = True
        await db.commit()
        return {"status": "amount_mismatch"}

    await accept_bid(
        db,
        project_id=intent.project_id,
        user_id=intent.user_id,
        amount_paise=intent.amount_paise,
        idempotency_key=intent.idempotency_key,
        razorpay_payment_id_for=lambda _intent: razorpay_payment_id,
        is_mock=False,
    )

    event.processed = True
    await db.commit()
    return {"status": "processed"}
