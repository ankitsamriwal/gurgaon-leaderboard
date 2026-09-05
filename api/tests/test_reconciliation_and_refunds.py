"""Phase 6 exit criterion (docs/07-implementation-plan.md): intentionally
desyncing a project's cached total from its ledger gets caught and
reported by the reconciliation job. Also covers docs/02's bid reversal
(refund/chargeback) endpoint and the leadership_log fix it required.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.db import engine


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


async def _seed_project(client: AsyncClient) -> uuid.UUID:
    resp = await client.post(
        "/internal/test/seed-project", json={"rera_number": f"RC-RECON-{uuid.uuid4().hex[:10]}"}
    )
    return uuid.UUID(resp.json()["project_id"])


async def _seed_user(client: AsyncClient) -> uuid.UUID:
    resp = await client.post("/internal/test/seed-user")
    return uuid.UUID(resp.json()["user_id"])


async def _settle(client: AsyncClient, project_id, user_id, amount_paise: int, idempotency_key: str) -> dict:
    resp = await client.post(
        "/internal/test/settle",
        json={
            "project_id": str(project_id),
            "user_id": str(user_id),
            "amount_paise": amount_paise,
            "idempotency_key": idempotency_key,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_reconciliation_catches_and_corrects_a_desynced_cache(client: AsyncClient):
    admin_token = await _make_admin(client, "+919888800001")
    project_id = await _seed_project(client)
    user_id = await _seed_user(client)

    await _settle(client, project_id, user_id, 300000, "recon-bid-1")

    # Intentionally desync the cache from the ledger (docs/07's test scenario).
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE projects SET cached_total_paise = 999999, total_bid_count = 42 WHERE id = :id"),
            {"id": str(project_id)},
        )

    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    resp = await client.post("/admin/reconciliation/run", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    report = resp.json()["report"]

    mismatch = next(m for m in report["mismatches"] if m["project_id"] == str(project_id))
    assert mismatch["cached_total_paise"] == 999999
    assert mismatch["ledger_total_paise"] == 300000
    assert mismatch["corrected"] is True

    resp = await client.get(f"/projects/{project_id}")
    assert resp.json()["total_paise"] == 300000
    assert resp.json()["bid_count"] == 1

    resp = await client.get("/admin/reconciliation/report", headers=admin_headers)
    assert resp.json()["report"]["id"] == report["id"]


@pytest.mark.asyncio
async def test_reconciliation_reports_no_mismatches_when_consistent(client: AsyncClient):
    admin_token = await _make_admin(client, "+919888800002")
    project_id = await _seed_project(client)
    user_id = await _seed_user(client)
    await _settle(client, project_id, user_id, 150000, "recon-bid-2")

    resp = await client.post(
        "/admin/reconciliation/run", headers={"Authorization": f"Bearer {admin_token}"}
    )
    report = resp.json()["report"]
    assert not any(m["project_id"] == str(project_id) for m in report["mismatches"])


@pytest.mark.asyncio
async def test_admin_can_reverse_a_bid_and_totals_adjust(client: AsyncClient):
    admin_token = await _make_admin(client, "+919888800003")
    project_id = await _seed_project(client)
    user_id = await _seed_user(client)

    settled = await _settle(client, project_id, user_id, 200000, "refund-bid-1")
    bid_id = settled["bid_id"]

    resp = await client.post(
        f"/admin/bids/{bid_id}/reverse", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["reversed"] is True

    resp = await client.get(f"/projects/{project_id}")
    assert resp.json()["total_paise"] == 0
    assert resp.json()["bid_count"] == 0

    # Reversal must be reflected in a fresh reconciliation pass too.
    recon = await client.post(
        "/admin/reconciliation/run", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert not any(m["project_id"] == str(project_id) for m in recon.json()["report"]["mismatches"])


@pytest.mark.asyncio
async def test_reversing_the_leader_hands_leadership_to_a_third_untouched_project(client: AsyncClient):
    """Regression test for the leadership_log fix: previously
    _update_leadership_log only checked whether the project the caller had
    just modified was the new leader, which is correct while totals only
    ever increase but breaks once a reversal knocks the leader down and an
    untouched third project should now be leader.
    """
    admin_token = await _make_admin(client, "+919888800004")
    project_a = await _seed_project(client)  # will lead, then get reversed
    project_b = await _seed_project(client)  # untouched — should inherit the lead
    user_id = await _seed_user(client)

    await _settle(client, project_a, user_id, 500000, "leader-a-bid")
    await _settle(client, project_b, user_id, 300000, "leader-b-bid")

    resp = await client.get("/projects/leaderboard")
    assert resp.json()["rankings"][0]["project_id"] == str(project_a)
    assert resp.json()["leader"]["project_id"] == str(project_a)

    # Find project_a's bid id to reverse it.
    resp = await client.get(f"/projects/{project_a}")
    bid_id = resp.json()["bids"]["items"][0]["id"]

    resp = await client.post(
        f"/admin/bids/{bid_id}/reverse", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert resp.status_code == 200

    resp = await client.get("/projects/leaderboard")
    body = resp.json()
    assert body["rankings"][0]["project_id"] == str(project_b), "project_b should now lead"
    assert body["leader"]["project_id"] == str(project_b), "leadership_log must reflect the new leader"
