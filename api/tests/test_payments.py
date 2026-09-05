"""Phase 3 exit criterion (docs/07-implementation-plan.md): a (test-mode)
end-to-end payment results in exactly one bids row, and replaying the same
webhook payload twice does not create a second row.

No real Razorpay account exists for this build, so order creation is
exercised through FastAPI's standard dependency_overrides mechanism (a
fake Orders API client) rather than a live call — everything downstream of
that (idempotency, HMAC signature verification, amount checks, the ledger
transaction) runs for real against Postgres.
"""

import hashlib
import hmac
import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.config import settings
from app.db import async_session
from app.main import app
from app.models import Bid, Project, WebhookEvent
from app.services.razorpay_client import get_razorpay_client

WEBHOOK_SECRET = "test-webhook-secret"


class FakeRazorpayClient:
    _counter = 0

    async def create_order(self, *, amount_paise: int, currency: str = "INR", receipt: str | None = None) -> dict:
        FakeRazorpayClient._counter += 1
        return {
            "id": f"order_fake{FakeRazorpayClient._counter}",
            "amount": amount_paise,
            "currency": currency,
            "status": "created",
        }


@pytest.fixture(autouse=True)
def _override_razorpay_client():
    app.dependency_overrides[get_razorpay_client] = lambda: FakeRazorpayClient()
    settings.razorpay_webhook_secret = WEBHOOK_SECRET
    yield
    app.dependency_overrides.pop(get_razorpay_client, None)


async def _signed_up_user(client: AsyncClient, phone: str) -> str:
    resp = await client.post("/auth/otp/request", json={"phone": phone})
    otp = resp.json()["debug_otp"]
    request_id = resp.json()["request_id"]
    resp = await client.post("/auth/otp/verify", json={"request_id": request_id, "otp": otp})
    return resp.json()["access_token"]


async def _seed_live_project(client: AsyncClient) -> uuid.UUID:
    resp = await client.post(
        "/internal/test/seed-project", json={"rera_number": f"RC-PAY-{uuid.uuid4().hex[:12]}"}
    )
    return uuid.UUID(resp.json()["project_id"])


def _sign(body: bytes) -> str:
    return hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()


def _captured_payload(*, order_id: str, payment_id: str, amount_paise: int) -> bytes:
    return json.dumps(
        {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": payment_id,
                        "amount": amount_paise,
                        "currency": "INR",
                        "status": "captured",
                        "order_id": order_id,
                    }
                }
            },
        }
    ).encode()


@pytest.mark.asyncio
async def test_create_intent_creates_order_and_is_idempotent(client: AsyncClient):
    token = await _signed_up_user(client, "+919999911001")
    project_id = await _seed_live_project(client)
    headers = {"Authorization": f"Bearer {token}"}

    body = {"project_id": str(project_id), "amount_paise": 150000, "idempotency_key": "click-1"}
    resp1 = await client.post("/payments/intent", json=body, headers=headers)
    assert resp1.status_code == 201, resp1.text

    resp2 = await client.post("/payments/intent", json=body, headers=headers)
    assert resp2.status_code == 201
    assert resp2.json()["intent_id"] == resp1.json()["intent_id"], "same idempotency_key must not create a 2nd order"


@pytest.mark.asyncio
async def test_webhook_end_to_end_creates_exactly_one_bid(client: AsyncClient):
    token = await _signed_up_user(client, "+919999911002")
    project_id = await _seed_live_project(client)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        "/payments/intent",
        json={"project_id": str(project_id), "amount_paise": 150000, "idempotency_key": "click-2"},
        headers=headers,
    )
    order_id = resp.json()["razorpay_order_id"]

    payload = _captured_payload(order_id=order_id, payment_id="pay_abc123", amount_paise=150000)
    signature = _sign(payload)

    resp = await client.post(
        "/webhooks/razorpay",
        content=payload,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": signature},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "processed"

    async with async_session() as session:
        project = await session.get(Project, project_id)
        bid_count = (
            await session.execute(select(func.count(Bid.id)).where(Bid.project_id == project_id))
        ).scalar_one()

    assert bid_count == 1
    assert project.cached_total_paise == 150000


@pytest.mark.asyncio
async def test_webhook_replay_does_not_duplicate(client: AsyncClient):
    token = await _signed_up_user(client, "+919999911003")
    project_id = await _seed_live_project(client)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        "/payments/intent",
        json={"project_id": str(project_id), "amount_paise": 200000, "idempotency_key": "click-3"},
        headers=headers,
    )
    order_id = resp.json()["razorpay_order_id"]

    payload = _captured_payload(order_id=order_id, payment_id="pay_replay1", amount_paise=200000)
    signature = _sign(payload)
    headers_wh = {"Content-Type": "application/json", "X-Razorpay-Signature": signature}

    resp1 = await client.post("/webhooks/razorpay", content=payload, headers=headers_wh)
    assert resp1.json()["status"] == "processed"

    # Razorpay's documented at-least-once delivery: the exact same payload
    # (and therefore signature) arrives again.
    resp2 = await client.post("/webhooks/razorpay", content=payload, headers=headers_wh)
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "already_processed"

    async with async_session() as session:
        project = await session.get(Project, project_id)
        bid_count = (
            await session.execute(select(func.count(Bid.id)).where(Bid.project_id == project_id))
        ).scalar_one()

    assert bid_count == 1
    assert project.cached_total_paise == 200000


@pytest.mark.asyncio
async def test_webhook_invalid_signature_is_rejected_and_logged(client: AsyncClient):
    payload = _captured_payload(order_id="order_doesnotmatter", payment_id="pay_bad", amount_paise=100000)

    resp = await client.post(
        "/webhooks/razorpay",
        content=payload,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": "not-a-real-signature"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_SIGNATURE"

    async with async_session() as session:
        event = (
            await session.execute(
                select(WebhookEvent).where(WebhookEvent.razorpay_event_id == "payment.captured:pay_bad")
            )
        ).scalar_one()

    assert event.signature_valid is False


@pytest.mark.asyncio
async def test_webhook_amount_mismatch_does_not_create_a_bid(client: AsyncClient):
    token = await _signed_up_user(client, "+919999911004")
    project_id = await _seed_live_project(client)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        "/payments/intent",
        json={"project_id": str(project_id), "amount_paise": 150000, "idempotency_key": "click-4"},
        headers=headers,
    )
    order_id = resp.json()["razorpay_order_id"]

    # Attacker/bug scenario: webhook claims a different (lower) amount than
    # what the intent was created for.
    payload = _captured_payload(order_id=order_id, payment_id="pay_mismatch", amount_paise=1)
    signature = _sign(payload)

    resp = await client.post(
        "/webhooks/razorpay",
        content=payload,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": signature},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "amount_mismatch"

    async with async_session() as session:
        bid_count = (
            await session.execute(select(func.count(Bid.id)).where(Bid.project_id == project_id))
        ).scalar_one()

    assert bid_count == 0
