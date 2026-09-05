"""Phase 2 exit criterion (docs/07-implementation-plan.md): a user can sign
up and get a valid session token; expired/rotated tokens are rejected.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.db import engine


async def _signup(client: AsyncClient, phone: str) -> dict:
    resp = await client.post("/auth/otp/request", json={"phone": phone})
    assert resp.status_code == 202, resp.text
    request_id = resp.json()["request_id"]
    otp = resp.json()["debug_otp"]
    assert otp is not None, "debug_otp should be present outside production"

    resp = await client.post("/auth/otp/verify", json={"request_id": request_id, "otp": otp})
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_otp_signup_issues_valid_tokens(client: AsyncClient):
    tokens = await _signup(client, "+919999900001")
    assert tokens["access_token"]
    assert tokens["refresh_token"]
    assert tokens["user"]["id"]


@pytest.mark.asyncio
async def test_wrong_otp_is_rejected_and_counts_as_an_attempt(client: AsyncClient):
    resp = await client.post("/auth/otp/request", json={"phone": "+919999900002"})
    request_id = resp.json()["request_id"]

    resp = await client.post("/auth/otp/verify", json={"request_id": request_id, "otp": "000000"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "OTP_INCORRECT"


@pytest.mark.asyncio
async def test_expired_otp_is_rejected(client: AsyncClient):
    resp = await client.post("/auth/otp/request", json={"phone": "+919999900003"})
    request_id = resp.json()["request_id"]
    otp = resp.json()["debug_otp"]

    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE otp_requests SET expires_at = now() - interval '1 minute' WHERE id = :id"),
            {"id": request_id},
        )

    resp = await client.post("/auth/otp/verify", json={"request_id": request_id, "otp": otp})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "OTP_EXPIRED"


@pytest.mark.asyncio
async def test_refresh_token_rotates_and_old_one_is_rejected(client: AsyncClient):
    tokens = await _signup(client, "+919999900004")
    old_refresh = tokens["refresh_token"]

    resp = await client.post("/auth/token/refresh", json={"refresh_token": old_refresh})
    assert resp.status_code == 200, resp.text
    new_tokens = resp.json()
    assert new_tokens["refresh_token"] != old_refresh

    # The old, now-rotated refresh token must never work again.
    resp = await client.post("/auth/token/refresh", json={"refresh_token": old_refresh})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "REFRESH_REUSED"


@pytest.mark.asyncio
async def test_refresh_reuse_revokes_the_whole_session_chain(client: AsyncClient):
    tokens = await _signup(client, "+919999900005")
    old_refresh = tokens["refresh_token"]

    resp = await client.post("/auth/token/refresh", json={"refresh_token": old_refresh})
    rotated_refresh = resp.json()["refresh_token"]

    # Replay the stolen/old token — this is the theft signal.
    resp = await client.post("/auth/token/refresh", json={"refresh_token": old_refresh})
    assert resp.status_code == 401

    # The legitimately-rotated token must now be dead too: the whole
    # session chain was revoked in response to the reuse (it was never
    # itself replayed, so the code reflects "revoked", not "reused").
    resp = await client.post("/auth/token/refresh", json={"refresh_token": rotated_refresh})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "REFRESH_REVOKED"


@pytest.mark.asyncio
async def test_unknown_refresh_token_is_rejected(client: AsyncClient):
    resp = await client.post("/auth/token/refresh", json={"refresh_token": str(uuid.uuid4())})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "REFRESH_INVALID"


@pytest.mark.asyncio
async def test_otp_request_is_rate_limited_per_phone(client: AsyncClient):
    phone = "+919999900099"
    for _ in range(5):
        resp = await client.post("/auth/otp/request", json={"phone": phone})
        assert resp.status_code == 202

    resp = await client.post("/auth/otp/request", json={"phone": phone})
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "RATE_LIMITED"


@pytest.mark.asyncio
async def test_logout_revokes_the_session(client: AsyncClient):
    tokens = await _signup(client, "+919999900006")
    refresh = tokens["refresh_token"]

    resp = await client.post("/auth/logout", json={"refresh_token": refresh})
    assert resp.status_code == 204

    resp = await client.post("/auth/token/refresh", json={"refresh_token": refresh})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "REFRESH_REVOKED"
