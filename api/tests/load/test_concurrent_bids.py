"""The release-gate test from docs/05-security-anti-fraud.md:

"Simulate concurrent 'beat the leader by ₹1' attempts against the same
project ... verify the SELECT ... FOR UPDATE transaction serializes
correctly under load and no double-counted or lost bid occurs."

Runs against a real Postgres (no mocking of the DB layer) via the internal
mock-settle endpoints, since Razorpay isn't wired up yet (Phase 1, per
docs/07-implementation-plan.md).
"""

import asyncio
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db import async_session
from app.models import Bid, Project

CONCURRENT_BIDDERS = 100
BID_AMOUNT_PAISE = 10_000


async def _seed_project(client: AsyncClient) -> uuid.UUID:
    resp = await client.post(
        "/internal/test/seed-project",
        json={"rera_number": f"RC-TEST-{uuid.uuid4().hex[:12]}"},
    )
    assert resp.status_code == 200, resp.text
    return uuid.UUID(resp.json()["project_id"])


async def _seed_user(client: AsyncClient) -> uuid.UUID:
    resp = await client.post("/internal/test/seed-user")
    assert resp.status_code == 200, resp.text
    return uuid.UUID(resp.json()["user_id"])


async def _settle(
    client: AsyncClient, project_id: uuid.UUID, user_id: uuid.UUID, amount_paise: int, idempotency_key: str
) -> dict:
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


async def _ledger_sum_and_count(project_id: uuid.UUID) -> tuple[int, int]:
    async with async_session() as session:
        row = (
            await session.execute(
                select(func.coalesce(func.sum(Bid.amount_paise), 0), func.count(Bid.id)).where(
                    Bid.project_id == project_id
                )
            )
        ).one()
        return row[0], row[1]


@pytest.mark.asyncio
async def test_concurrent_bids_on_same_project_never_double_count_or_lose_a_bid(client: AsyncClient):
    project_id = await _seed_project(client)
    user_ids = await asyncio.gather(*[_seed_user(client) for _ in range(CONCURRENT_BIDDERS)])

    results = await asyncio.gather(
        *[
            _settle(client, project_id, user_ids[i], BID_AMOUNT_PAISE, f"bid-{uuid.uuid4()}")
            for i in range(CONCURRENT_BIDDERS)
        ]
    )

    assert all(not r["already_settled"] for r in results), "each distinct bid must settle exactly once"
    assert len({r["bid_id"] for r in results}) == CONCURRENT_BIDDERS, "no two bids should collapse into one"

    async with async_session() as session:
        project = await session.get(Project, project_id)

    ledger_sum, ledger_count = await _ledger_sum_and_count(project_id)

    assert ledger_count == CONCURRENT_BIDDERS
    assert ledger_sum == CONCURRENT_BIDDERS * BID_AMOUNT_PAISE
    assert project.total_bid_count == CONCURRENT_BIDDERS
    assert project.cached_total_paise == ledger_sum, (
        "cached_total_paise must always match SUM(bids.amount_paise) — "
        "the cache is derived, never a separate source of truth"
    )


@pytest.mark.asyncio
async def test_duplicate_idempotency_key_settled_concurrently_still_counts_once(client: AsyncClient):
    project_id = await _seed_project(client)
    user_id = await _seed_user(client)
    idempotency_key = f"double-tap-{uuid.uuid4()}"

    results = await asyncio.gather(
        *[_settle(client, project_id, user_id, BID_AMOUNT_PAISE, idempotency_key) for _ in range(10)]
    )

    assert len({r["bid_id"] for r in results}) == 1, "a retried/double-tapped click must never double-count"

    async with async_session() as session:
        project = await session.get(Project, project_id)

    ledger_sum, ledger_count = await _ledger_sum_and_count(project_id)

    assert ledger_count == 1
    assert ledger_sum == BID_AMOUNT_PAISE
    assert project.total_bid_count == 1
    assert project.cached_total_paise == BID_AMOUNT_PAISE
