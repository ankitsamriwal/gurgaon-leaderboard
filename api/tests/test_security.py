"""Phase 7 exit criterion (docs/07-implementation-plan.md): rate limits
verified with a script that intentionally exceeds each limit and confirms
a 429. Also covers the CAPTCHA provider abstraction and the wash-trading
flag queries from docs/05.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.config import settings
from app.db import engine
from app.main import app
from app.services.captcha_provider import NoopCaptchaProvider, TurnstileProvider, get_captcha_provider
from app.services.razorpay_client import get_razorpay_client


class _FakeRazorpayClient:
    _counter = 0

    async def create_order(self, *, amount_paise: int, currency: str = "INR", receipt: str | None = None) -> dict:
        _FakeRazorpayClient._counter += 1
        return {"id": f"order_sec{_FakeRazorpayClient._counter}", "amount": amount_paise, "currency": currency}


async def _signed_up_user(client: AsyncClient, phone: str) -> tuple[str, str]:
    resp = await client.post("/auth/otp/request", json={"phone": phone})
    otp = resp.json()["debug_otp"]
    request_id = resp.json()["request_id"]
    resp = await client.post("/auth/otp/verify", json={"request_id": request_id, "otp": otp})
    body = resp.json()
    return body["access_token"], body["user"]["id"]


async def _make_admin(client: AsyncClient, phone: str) -> str:
    _, user_id = await _signed_up_user(client, phone)
    await client.post("/internal/test/promote-role", json={"user_id": user_id, "role": "admin"})
    fresh_token, _ = await _signed_up_user(client, phone)
    return fresh_token


async def _seed_live_project(client: AsyncClient) -> uuid.UUID:
    resp = await client.post(
        "/internal/test/seed-project", json={"rera_number": f"RC-SEC-{uuid.uuid4().hex[:12]}"}
    )
    return uuid.UUID(resp.json()["project_id"])


async def _seed_user(client: AsyncClient) -> str:
    resp = await client.post("/internal/test/seed-user")
    return resp.json()["user_id"]


async def _settle(client: AsyncClient, project_id, user_id: str, amount_paise: int, idempotency_key: str) -> dict:
    resp = await client.post(
        "/internal/test/settle",
        json={
            "project_id": str(project_id),
            "user_id": user_id,
            "amount_paise": amount_paise,
            "idempotency_key": idempotency_key,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_otp_request_is_rate_limited_per_ip_across_different_phones(client: AsyncClient):
    # ASGITransport gives every test request the same synthetic client IP,
    # so distinct phone numbers isolate this from the per-phone limit
    # (docs/05: 10/hour per IP, separate from 5/hour per phone).
    for i in range(10):
        resp = await client.post("/auth/otp/request", json={"phone": f"+9199999{i:05d}"})
        assert resp.status_code == 202, resp.text

    resp = await client.post("/auth/otp/request", json={"phone": "+919999999999"})
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "RATE_LIMITED"


@pytest.mark.asyncio
async def test_payments_intent_is_rate_limited_per_user(client: AsyncClient):
    app.dependency_overrides[get_razorpay_client] = lambda: _FakeRazorpayClient()
    try:
        token, _ = await _signed_up_user(client, "+919777700001")
        project_id = await _seed_live_project(client)
        headers = {"Authorization": f"Bearer {token}"}

        for i in range(20):
            resp = await client.post(
                "/payments/intent",
                json={"project_id": str(project_id), "amount_paise": 1000, "idempotency_key": f"rl-{i}"},
                headers=headers,
            )
            assert resp.status_code == 201, resp.text

        resp = await client.post(
            "/payments/intent",
            json={"project_id": str(project_id), "amount_paise": 1000, "idempotency_key": "rl-final"},
            headers=headers,
        )
        assert resp.status_code == 429
        assert resp.json()["error"]["code"] == "RATE_LIMITED"
    finally:
        app.dependency_overrides.pop(get_razorpay_client, None)


@pytest.mark.asyncio
async def test_captcha_verification_is_enforced_when_it_fails(client: AsyncClient, monkeypatch):
    """NoopCaptchaProvider always passes in tests (no real site key exists
    for this build) — swap in a fake that fails, to prove the check is
    actually wired into the request path, not just present in code."""
    from app.routers import auth as auth_router_module

    class AlwaysFailCaptcha:
        async def verify(self, token):
            return False

    monkeypatch.setattr(auth_router_module, "get_captcha_provider", lambda: AlwaysFailCaptcha())

    resp = await client.post("/auth/otp/request", json={"phone": "+919777700099"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "CAPTCHA_FAILED"


def test_captcha_provider_selection():
    assert isinstance(get_captcha_provider(), NoopCaptchaProvider)

    original_env = settings.environment
    original_secret = settings.turnstile_secret_key
    try:
        settings.environment = "production"
        settings.turnstile_secret_key = ""
        with pytest.raises(RuntimeError):
            get_captcha_provider()

        settings.turnstile_secret_key = "fake-secret"
        assert isinstance(get_captcha_provider(), TurnstileProvider)
    finally:
        settings.environment = original_env
        settings.turnstile_secret_key = original_secret


@pytest.mark.asyncio
async def test_repeated_bidder_flag_fires_for_same_user_same_project(client: AsyncClient):
    project_id = await _seed_live_project(client)
    user_id = await _seed_user(client)

    for i in range(3):
        await _settle(client, project_id, user_id, 1000, f"wash-{i}")

    admin_token = await _make_admin(client, "+919777700002")
    resp = await client.get("/admin/anti-fraud/flags", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    flags = resp.json()["repeated_bidder_flags"]
    assert any(f["user_id"] == user_id and f["project_id"] == str(project_id) for f in flags)


@pytest.mark.asyncio
async def test_new_account_cluster_flag_fires(client: AsyncClient):
    project_id = await _seed_live_project(client)

    for i in range(5):
        user_id = await _seed_user(client)
        await _settle(client, project_id, user_id, 500, f"newacct-{i}")

    admin_token = await _make_admin(client, "+919777700003")
    resp = await client.get("/admin/anti-fraud/flags", headers={"Authorization": f"Bearer {admin_token}"})
    flags = resp.json()["new_account_cluster_flags"]
    assert any(f["project_id"] == str(project_id) for f in flags)


@pytest.mark.asyncio
async def test_velocity_spike_flag_fires_against_a_quiet_baseline(client: AsyncClient):
    project_id = await _seed_live_project(client)
    baseline_user_id = await _seed_user(client)

    # A quiet baseline bid from 3 days ago...
    await _settle(client, project_id, baseline_user_id, 100, "velocity-baseline")
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE bids SET created_at = now() - interval '3 days' "
                "WHERE payment_intent_id = (SELECT id FROM payment_intents WHERE idempotency_key = 'velocity-baseline')"
            )
        )

    # ...then a sudden burst of bids right now.
    for i in range(6):
        burst_user_id = await _seed_user(client)
        await _settle(client, project_id, burst_user_id, 100, f"velocity-burst-{i}")

    admin_token = await _make_admin(client, "+919777700004")
    resp = await client.get("/admin/anti-fraud/flags", headers={"Authorization": f"Bearer {admin_token}"})
    flags = resp.json()["velocity_spike_flags"]
    assert any(f["project_id"] == str(project_id) for f in flags)
