"""Phase 5 exit criterion (docs/07-implementation-plan.md): a settled
webhook-verified bid updates the leaderboard for all connected clients
within a few seconds, without a page refresh.

This tests the actual mechanism end to end — a real Redis subscriber
receives the real published payload after a real webhook-settled bid —
without going through the WebSocket transport itself. The `@router.websocket`
handler in app/routers/ws.py is thin, standard FastAPI/Starlette code;
testing it in-process here would need to bridge the test's asyncpg/Redis
connections across a different event loop (the same class of problem
Phase 1 hit and fixed for HTTP — see tests/conftest.py's `event_loop`
fixture), which isn't worth solving just to exercise boilerplate. Smoke-test
the live socket manually (e.g. with `websocat` or a browser) once deployed.
"""

import asyncio
import hashlib
import hmac
import json
import uuid

import pytest
from httpx import AsyncClient

from app.config import settings
from app.main import app
from app.redis_client import redis_client
from app.services.projects import LEADERBOARD_WS_CHANNEL
from app.services.razorpay_client import get_razorpay_client

WEBHOOK_SECRET = "test-webhook-secret-realtime"


class FakeRazorpayClient:
    _counter = 0

    async def create_order(self, *, amount_paise: int, currency: str = "INR", receipt: str | None = None) -> dict:
        FakeRazorpayClient._counter += 1
        return {"id": f"order_rt{FakeRazorpayClient._counter}", "amount": amount_paise, "currency": currency}


@pytest.fixture(autouse=True)
def _override_razorpay_client():
    app.dependency_overrides[get_razorpay_client] = lambda: FakeRazorpayClient()
    settings.razorpay_webhook_secret = WEBHOOK_SECRET
    yield
    app.dependency_overrides.pop(get_razorpay_client, None)


def _sign(body: bytes) -> str:
    return hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()


async def _signed_up_user(client: AsyncClient, phone: str) -> str:
    resp = await client.post("/auth/otp/request", json={"phone": phone})
    otp = resp.json()["debug_otp"]
    request_id = resp.json()["request_id"]
    resp = await client.post("/auth/otp/verify", json={"request_id": request_id, "otp": otp})
    return resp.json()["access_token"]


async def _seed_live_project(client: AsyncClient) -> uuid.UUID:
    resp = await client.post(
        "/internal/test/seed-project", json={"rera_number": f"RC-RT-{uuid.uuid4().hex[:12]}"}
    )
    return uuid.UUID(resp.json()["project_id"])


@pytest.mark.asyncio
async def test_settled_webhook_bid_publishes_leaderboard_update_over_pubsub(client: AsyncClient):
    project_id = await _seed_live_project(client)
    token = await _signed_up_user(client, "+919999933001")
    headers = {"Authorization": f"Bearer {token}"}

    pubsub = redis_client.pubsub()
    await pubsub.subscribe(LEADERBOARD_WS_CHANNEL)
    try:
        # Drain the subscribe-confirmation message before triggering the bid.
        await pubsub.get_message(timeout=2)

        resp = await client.post(
            "/payments/intent",
            json={"project_id": str(project_id), "amount_paise": 175000, "idempotency_key": "rt-click-1"},
            headers=headers,
        )
        order_id = resp.json()["razorpay_order_id"]

        payload = json.dumps(
            {
                "event": "payment.captured",
                "payload": {
                    "payment": {
                        "entity": {
                            "id": "pay_rt1",
                            "amount": 175000,
                            "currency": "INR",
                            "status": "captured",
                            "order_id": order_id,
                        }
                    }
                },
            }
        ).encode()
        resp = await client.post(
            "/webhooks/razorpay",
            content=payload,
            headers={"Content-Type": "application/json", "X-Razorpay-Signature": _sign(payload)},
        )
        assert resp.json()["status"] == "processed"

        message = None
        for _ in range(20):
            message = await pubsub.get_message(timeout=1)
            if message is not None and message["type"] == "message":
                break
        assert message is not None, "no leaderboard update was published within the timeout"

        broadcast = json.loads(message["data"])
        assert any(r["project_id"] == str(project_id) for r in broadcast["rankings"])
        matching = next(r for r in broadcast["rankings"] if r["project_id"] == str(project_id))
        assert matching["total_paise"] == 175000
    finally:
        await pubsub.unsubscribe(LEADERBOARD_WS_CHANNEL)
        await pubsub.aclose()


@pytest.mark.asyncio
async def test_ws_route_is_registered(client: AsyncClient):
    paths = {route.path for route in app.routes}
    assert "/ws/leaderboard" in paths
