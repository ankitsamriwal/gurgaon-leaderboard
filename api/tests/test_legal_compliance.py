"""Phase 8 (docs/07-implementation-plan.md): disclaimers, verified-listing
badges, and RERA-verified badges are frontend concerns tested manually in
Phase 5's browser pass. This covers the backend capabilities docs/06
requires: the dispute/takedown fast path and the DPDP data export/delete
flow. The phase's actual exit criterion — legal review sign-off — is
external and cannot be satisfied by any test in this repo; see the
top-level README.
"""

import uuid

import pytest
from httpx import AsyncClient


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
        "/internal/test/seed-project", json={"rera_number": f"RC-LEGAL-{uuid.uuid4().hex[:10]}"}
    )
    return uuid.UUID(resp.json()["project_id"])


@pytest.mark.asyncio
async def test_dispute_is_filed_and_appears_in_priority_admin_queue(client: AsyncClient):
    project_id = await _seed_live_project(client)
    token, _ = await _signed_up_user(client, "+919666600001")

    resp = await client.post(
        f"/projects/{project_id}/dispute",
        json={"reason": "This is our project, we never submitted it", "contact_email": "legal@realdeveloper.test"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 202, resp.text
    dispute_id = resp.json()["dispute_id"]

    admin_token = await _make_admin(client, "+919666600002")
    resp = await client.get("/admin/disputes/pending", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    disputes = resp.json()["disputes"]
    match = next(d for d in disputes if d["id"] == dispute_id)
    assert match["priority"] is True
    assert match["project_id"] == str(project_id)


@pytest.mark.asyncio
async def test_resolving_a_dispute_can_suspend_the_project(client: AsyncClient):
    project_id = await _seed_live_project(client)
    token, _ = await _signed_up_user(client, "+919666600003")

    resp = await client.post(
        f"/projects/{project_id}/dispute",
        json={"reason": "Fraudulent RERA number"},
        headers={"Authorization": f"Bearer {token}"},
    )
    dispute_id = resp.json()["dispute_id"]

    admin_token = await _make_admin(client, "+919666600004")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    resp = await client.post(
        f"/admin/disputes/{dispute_id}/resolve",
        json={"notes": "Confirmed fraudulent, suspending", "suspend_project": True},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "resolved"

    resp = await client.get("/projects/leaderboard")
    assert all(r["project_id"] != str(project_id) for r in resp.json()["rankings"])

    resp = await client.get(f"/projects/{project_id}")
    assert resp.status_code == 404, "a suspended project must not be publicly visible"


@pytest.mark.asyncio
async def test_admin_can_suspend_a_live_project_directly(client: AsyncClient):
    project_id = await _seed_live_project(client)
    admin_token = await _make_admin(client, "+919666600005")

    resp = await client.post(
        f"/admin/projects/{project_id}/suspend",
        json={"reason": "wash trading detected"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "suspended"

    resp = await client.get(f"/projects/{project_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_data_export_request_is_filed_and_fulfillable(client: AsyncClient):
    token, user_id = await _signed_up_user(client, "+919666600006")

    resp = await client.post(
        "/account/data-request", json={"request_type": "export"}, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 202, resp.text
    request_id = resp.json()["request_id"]

    admin_token = await _make_admin(client, "+919666600007")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    resp = await client.get("/admin/data-requests/pending", headers=admin_headers)
    assert any(r["id"] == request_id for r in resp.json()["requests"])

    resp = await client.post(f"/admin/data-requests/{request_id}/fulfill", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "fulfilled"


@pytest.mark.asyncio
async def test_data_delete_request_anonymizes_without_breaking_ledger_integrity(client: AsyncClient):
    """docs/06: payment/ledger records must be retained even after a
    deletion request — deletion must anonymize, never cascade-delete a
    user with existing bids."""
    project_id = await _seed_live_project(client)
    token, user_id = await _signed_up_user(client, "+919666600008")

    settle_resp = await client.post(
        "/internal/test/settle",
        json={
            "project_id": str(project_id),
            "user_id": user_id,
            "amount_paise": 5000,
            "idempotency_key": "legal-delete-bid",
        },
    )
    assert settle_resp.status_code == 200

    resp = await client.post(
        "/account/data-request", json={"request_type": "delete"}, headers={"Authorization": f"Bearer {token}"}
    )
    request_id = resp.json()["request_id"]

    admin_token = await _make_admin(client, "+919666600009")
    resp = await client.post(
        f"/admin/data-requests/{request_id}/fulfill", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert resp.status_code == 200

    # The ledger and cached total must be untouched — this is what makes
    # anonymize-not-delete correct.
    resp = await client.get(f"/projects/{project_id}")
    assert resp.json()["total_paise"] == 5000
    assert resp.json()["bid_count"] == 1
