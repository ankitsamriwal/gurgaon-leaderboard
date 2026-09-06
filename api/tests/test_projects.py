"""Listing flow: a submission through the standardized template goes
straight onto the public leaderboard with its Rs 500 mock opening bid
("bidding starts from Rs 500"); admins moderate after the fact via
suspend/reject.
"""

import uuid

import pytest
from httpx import AsyncClient

VALID_RERA = "RC/REP/HARERA/GGM/523/240/2021/99"


async def _signed_up_user(client: AsyncClient, phone: str) -> tuple[str, str]:
    resp = await client.post("/auth/otp/request", json={"phone": phone})
    otp = resp.json()["debug_otp"]
    request_id = resp.json()["request_id"]
    resp = await client.post("/auth/otp/verify", json={"request_id": request_id, "otp": otp})
    body = resp.json()
    return body["access_token"], body["user"]["id"]


async def _make_admin(client: AsyncClient, phone: str) -> str:
    _, user_id = await _signed_up_user(client, phone)
    resp = await client.post("/internal/test/promote-role", json={"user_id": user_id, "role": "admin"})
    assert resp.status_code == 200, resp.text

    # The role claim is embedded in the access token at issuance (docs/00's
    # JWT sessions) — promoting the DB row doesn't retroactively upgrade an
    # already-issued token, so re-authenticate to pick up the new role.
    fresh_token, _ = await _signed_up_user(client, phone)
    return fresh_token


@pytest.mark.asyncio
async def test_submitted_project_goes_live_with_opening_bid_and_template(client: AsyncClient):
    token, _ = await _signed_up_user(client, "+919999922001")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        "/projects",
        json={
            "name": "Test Towers",
            "developer_name": "Test Developer",
            "locality": "Sector 50",
            "rera_number": VALID_RERA,
            "logo_url": "https://example.com/logo.png",
            "property_type": "apartment",
            "unit_sizes": "3 & 4 BHK",
            "amenities": "Clubhouse, Swimming pool",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "live"
    project_id = resp.json()["project_id"]

    # Straight onto the public leaderboard at exactly Rs 500 - the mock
    # opening bid every entry starts with.
    resp = await client.get("/projects/leaderboard")
    row = next(r for r in resp.json()["rankings"] if r["project_id"] == project_id)
    assert row["total_paise"] == 50000
    assert row["bid_count"] == 1
    assert row["property_type"] == "apartment"
    assert row["unit_sizes"] == "3 & 4 BHK"
    assert row["amenities"] == "Clubhouse, Swimming pool"
    assert row["logo_url"] == "https://example.com/logo.png"
    assert row["is_sample"] is False

    resp = await client.get(f"/projects/{project_id}")
    assert resp.status_code == 200
    assert resp.json()["property_type"] == "apartment"


@pytest.mark.asyncio
async def test_invalid_property_type_is_rejected(client: AsyncClient):
    token, _ = await _signed_up_user(client, "+919999922012")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        "/projects",
        json={
            "name": "Test Villas",
            "developer_name": "Test Developer",
            "locality": "Sector 51",
            "rera_number": VALID_RERA,
            "property_type": "castle",
        },
        headers=headers,
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "PROPERTY_TYPE_INVALID"


@pytest.mark.asyncio
async def test_invalid_rera_format_is_rejected(client: AsyncClient):
    token, _ = await _signed_up_user(client, "+919999922002")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        "/projects",
        json={"name": "X", "developer_name": "Y", "locality": "Z", "rera_number": "not-a-real-number"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "RERA_INVALID_FORMAT"


@pytest.mark.asyncio
async def test_duplicate_rera_number_is_rejected(client: AsyncClient):
    token, _ = await _signed_up_user(client, "+919999922003")
    headers = {"Authorization": f"Bearer {token}"}
    body = {"name": "A", "developer_name": "B", "locality": "C", "rera_number": VALID_RERA}

    resp = await client.post("/projects", json=body, headers=headers)
    assert resp.status_code == 201

    resp = await client.post("/projects", json={**body, "name": "A2"}, headers=headers)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "RERA_DUPLICATE"


@pytest.mark.asyncio
async def test_project_submission_is_rate_limited(client: AsyncClient):
    token, _ = await _signed_up_user(client, "+919999922004")
    headers = {"Authorization": f"Bearer {token}"}

    for i in range(3):
        resp = await client.post(
            "/projects",
            json={
                "name": f"Proj {i}",
                "developer_name": "D",
                "locality": "L",
                "rera_number": f"RC/REP/HARERA/GGM/{i}/1/2021/1",
            },
            headers=headers,
        )
        assert resp.status_code == 201

    resp = await client.post(
        "/projects",
        json={"name": "Proj 4", "developer_name": "D", "locality": "L", "rera_number": "RC/REP/HARERA/GGM/4/1/2021/1"},
        headers=headers,
    )
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "RATE_LIMITED"


@pytest.mark.asyncio
async def test_admin_suspend_pulls_project_off_the_leaderboard(client: AsyncClient):
    submitter_token, _ = await _signed_up_user(client, "+919999922005")
    admin_token = await _make_admin(client, "+919999922006")

    resp = await client.post(
        "/projects",
        json={"name": "Skyline", "developer_name": "Dev Co", "locality": "Sector 1", "rera_number": VALID_RERA},
        headers={"Authorization": f"Bearer {submitter_token}"},
    )
    project_id = resp.json()["project_id"]

    # Live immediately...
    resp = await client.get("/projects/leaderboard")
    assert any(r["project_id"] == project_id for r in resp.json()["rankings"])

    # ...until an admin suspends it.
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    resp = await client.post(
        f"/admin/projects/{project_id}/suspend",
        json={"reason": "moderation spot-check"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "suspended"

    resp = await client.get("/projects/leaderboard")
    assert all(r["project_id"] != project_id for r in resp.json()["rankings"])

    resp = await client.get(f"/projects/{project_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_rejection_keeps_project_off_the_leaderboard(client: AsyncClient):
    submitter_token, _ = await _signed_up_user(client, "+919999922007")
    admin_token = await _make_admin(client, "+919999922008")

    resp = await client.post(
        "/projects",
        json={"name": "Ghost Towers", "developer_name": "Dev Co", "locality": "Sector 2", "rera_number": VALID_RERA},
        headers={"Authorization": f"Bearer {submitter_token}"},
    )
    project_id = resp.json()["project_id"]

    resp = await client.post(
        f"/admin/projects/{project_id}/reject",
        json={"reason": "duplicate listing under a different name"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"

    resp = await client.get("/projects/leaderboard")
    assert all(r["project_id"] != project_id for r in resp.json()["rankings"])


@pytest.mark.asyncio
async def test_non_admin_cannot_approve_projects(client: AsyncClient):
    token, _ = await _signed_up_user(client, "+919999922009")
    resp = await client.post(
        f"/admin/projects/{uuid.uuid4()}/approve", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_claim_flow_promotes_claimant_to_developer_role(client: AsyncClient):
    submitter_token, _ = await _signed_up_user(client, "+919999922010")
    admin_token = await _make_admin(client, "+919999922011")
    claimant_token, claimant_id = await _signed_up_user(client, "+919999922012")

    resp = await client.post(
        "/projects",
        json={"name": "Claimable", "developer_name": "Dev Co", "locality": "S3", "rera_number": VALID_RERA},
        headers={"Authorization": f"Bearer {submitter_token}"},
    )
    project_id = resp.json()["project_id"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    await client.post(f"/admin/projects/{project_id}/approve", headers=admin_headers)

    resp = await client.post(
        f"/projects/{project_id}/claim",
        json={"document_url": "https://example.test/doc.pdf"},
        headers={"Authorization": f"Bearer {claimant_token}"},
    )
    assert resp.status_code == 202
    claim_id = resp.json()["claim_id"]

    resp = await client.post(f"/admin/claims/{claim_id}/approve", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"

    resp = await client.get(f"/projects/{project_id}")
    assert resp.json()["is_verified_developer_listing"] is True
