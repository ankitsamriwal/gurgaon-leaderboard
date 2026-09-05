"""Phase 9 exit criterion (docs/07-implementation-plan.md): a simulated
incident (e.g. kill the API pod mid-transaction) leaves the ledger
consistent on restart, and alerts fire as expected.

"Kill the process" is simulated by performing the exact same writes
accept_bid() would, then abandoning the session without committing —
which is what actually happens when a process dies mid-transaction: the
DB server detects the dropped connection and rolls back automatically.
This is the real mechanism the exit criterion is about, not a mock of it.
"""

import logging
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db import async_session
from app.models import Bid, PaymentIntent, Project
from app.services.reconciliation import run_reconciliation


async def _seed_live_project(client: AsyncClient) -> uuid.UUID:
    resp = await client.post(
        "/internal/test/seed-project", json={"rera_number": f"RC-LAUNCH-{uuid.uuid4().hex[:10]}"}
    )
    return uuid.UUID(resp.json()["project_id"])


async def _seed_user(client: AsyncClient) -> uuid.UUID:
    resp = await client.post("/internal/test/seed-user")
    return uuid.UUID(resp.json()["user_id"])


@pytest.mark.asyncio
async def test_process_death_mid_transaction_leaves_ledger_consistent(client: AsyncClient):
    project_id = await _seed_live_project(client)
    user_id = await _seed_user(client)

    async with async_session() as session:
        before = await session.get(Project, project_id)
        before_total = before.cached_total_paise
        before_count = before.total_bid_count

    # Simulate the process dying partway through the bid-acceptance
    # transaction: do the exact same writes accept_bid() does, but never
    # call commit(), then abandon the session — an aborted connection is
    # exactly what a killed process looks like to Postgres.
    crashed_session = async_session()
    try:
        project = (
            await crashed_session.execute(select(Project).where(Project.id == project_id).with_for_update())
        ).scalar_one()

        intent = PaymentIntent(
            project_id=project_id,
            user_id=user_id,
            amount_paise=999999,
            idempotency_key="crash-sim-intent",
            status="order_created",
        )
        crashed_session.add(intent)
        await crashed_session.flush()

        bid = Bid(
            project_id=project_id,
            user_id=user_id,
            payment_intent_id=intent.id,
            razorpay_payment_id="crash_sim_payment",
            amount_paise=999999,
        )
        crashed_session.add(bid)
        project.cached_total_paise += 999999
        project.total_bid_count += 1
        await crashed_session.flush()
        # <-- process "dies" here, before commit()
    finally:
        await crashed_session.close()  # no commit ever happened

    # "Restart": open a brand new session/connection, as a fresh process
    # would, and confirm nothing from the crashed transaction persisted.
    async with async_session() as session:
        after = await session.get(Project, project_id)
        assert after.cached_total_paise == before_total
        assert after.total_bid_count == before_count

        ledger_sum = (
            await session.execute(select(func.coalesce(func.sum(Bid.amount_paise), 0)).where(Bid.project_id == project_id))
        ).scalar_one()
        assert ledger_sum == before_total, "cached_total_paise must still match the ledger after the crash"

        orphaned_intent = (
            await session.execute(select(PaymentIntent).where(PaymentIntent.idempotency_key == "crash-sim-intent"))
        ).scalar_one_or_none()
        assert orphaned_intent is None, "the uncommitted intent must not have survived either"

    # A reconciliation run afterward should find nothing to fix — proof
    # the ledger is genuinely consistent, not just "close enough".
    async with async_session() as session:
        report = await run_reconciliation(session)
    assert not any(m["project_id"] == str(project_id) for m in report["mismatches"])


@pytest.mark.asyncio
async def test_reconciliation_mismatch_actually_logs_an_alert(client: AsyncClient, caplog):
    """docs/03: mismatches must be logged before being auto-corrected —
    this is the hook a real deployment wires to Slack/PagerDuty. Confirm
    it actually fires, not just that the code path exists."""
    from sqlalchemy import text

    project_id = await _seed_live_project(client)

    async with async_session() as session:
        await session.execute(
            text("UPDATE projects SET cached_total_paise = 55555 WHERE id = :id"), {"id": str(project_id)}
        )
        await session.commit()

    with caplog.at_level(logging.ERROR, logger="reconciliation"):
        async with async_session() as session:
            await run_reconciliation(session)

    assert any(
        "reconciliation mismatch" in record.message and str(project_id) in record.message
        for record in caplog.records
    ), "a real mismatch must produce an ERROR-level log line an alerting pipeline can pick up"


@pytest.mark.asyncio
async def test_webhook_amount_mismatch_logs_an_alert(client: AsyncClient, caplog, monkeypatch):
    """Same alerting-hook check for the other place docs/03 requires one:
    a webhook whose amount doesn't match its intent."""
    import hashlib
    import hmac
    import json

    from app.config import settings
    from app.main import app
    from app.services.razorpay_client import get_razorpay_client

    class FakeRazorpayClient:
        async def create_order(self, *, amount_paise, currency="INR", receipt=None):
            return {"id": f"order_launch_{uuid.uuid4().hex[:8]}", "amount": amount_paise, "currency": currency}

    app.dependency_overrides[get_razorpay_client] = lambda: FakeRazorpayClient()
    settings.razorpay_webhook_secret = "launch-readiness-secret"
    try:
        project_id = await _seed_live_project(client)
        resp = await client.post("/auth/otp/request", json={"phone": "+919555500001"})
        otp, request_id = resp.json()["debug_otp"], resp.json()["request_id"]
        resp = await client.post("/auth/otp/verify", json={"request_id": request_id, "otp": otp})
        token = resp.json()["access_token"]

        resp = await client.post(
            "/payments/intent",
            json={"project_id": str(project_id), "amount_paise": 150000, "idempotency_key": "launch-mismatch"},
            headers={"Authorization": f"Bearer {token}"},
        )
        order_id = resp.json()["razorpay_order_id"]

        payload = json.dumps(
            {
                "event": "payment.captured",
                "payload": {
                    "payment": {
                        "entity": {"id": "pay_launch_mismatch", "amount": 1, "order_id": order_id, "status": "captured"}
                    }
                },
            }
        ).encode()
        signature = hmac.new(b"launch-readiness-secret", payload, hashlib.sha256).hexdigest()

        with caplog.at_level(logging.ERROR, logger="webhooks"):
            resp = await client.post(
                "/webhooks/razorpay",
                content=payload,
                headers={"Content-Type": "application/json", "X-Razorpay-Signature": signature},
            )
        assert resp.json()["status"] == "amount_mismatch"
        assert any("webhook amount mismatch" in r.message for r in caplog.records)
    finally:
        app.dependency_overrides.pop(get_razorpay_client, None)
