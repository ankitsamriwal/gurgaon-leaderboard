"""Broader load test for Phase 9 (docs/07-implementation-plan.md): "Full
staging load test against Razorpay test mode mirroring expected launch
traffic." No real Razorpay account or staging environment exists for
this build (same gap noted throughout — see the top-level README), so
this substitutes the mixed read/write pattern a launch would actually see
— concurrent bidding across *several* projects at once plus concurrent
leaderboard reads — run against real Postgres/Redis. Phase 1's
same-project hot-path test remains the actual release gate for the
locking/correctness concern; this one is about the ledger staying correct
under a broader, more realistic traffic shape.
"""

import asyncio
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db import async_session
from app.models import Bid, Project

PROJECT_COUNT = 5
BIDDERS_PER_PROJECT = 20
CONCURRENT_READERS = 10
BID_AMOUNT_PAISE = 5_000


async def _seed_project(client: AsyncClient) -> uuid.UUID:
    resp = await client.post(
        "/internal/test/seed-project", json={"rera_number": f"RC-MIX-{uuid.uuid4().hex[:12]}"}
    )
    return uuid.UUID(resp.json()["project_id"])


async def _seed_user(client: AsyncClient) -> uuid.UUID:
    resp = await client.post("/internal/test/seed-user")
    return uuid.UUID(resp.json()["user_id"])


async def _settle(client: AsyncClient, project_id, user_id, idempotency_key: str) -> dict:
    resp = await client.post(
        "/internal/test/settle",
        json={
            "project_id": str(project_id),
            "user_id": str(user_id),
            "amount_paise": BID_AMOUNT_PAISE,
            "idempotency_key": idempotency_key,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _read_leaderboard_repeatedly(client: AsyncClient, times: int) -> None:
    for _ in range(times):
        resp = await client.get("/projects/leaderboard")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_concurrent_bidding_across_many_projects_with_concurrent_reads(client: AsyncClient):
    project_ids = [await _seed_project(client) for _ in range(PROJECT_COUNT)]
    user_ids = await asyncio.gather(*[_seed_user(client) for _ in range(PROJECT_COUNT * BIDDERS_PER_PROJECT)])

    write_tasks = []
    idx = 0
    for project_id in project_ids:
        for _ in range(BIDDERS_PER_PROJECT):
            write_tasks.append(
                _settle(client, project_id, user_ids[idx], f"mix-{project_id}-{uuid.uuid4()}")
            )
            idx += 1

    read_tasks = [_read_leaderboard_repeatedly(client, 5) for _ in range(CONCURRENT_READERS)]

    # Different projects never contend for the same row lock, so this
    # exercises real cross-project concurrency, not the same-project
    # serialization Phase 1's test targets — plus reads interleaved
    # throughout, mirroring actual launch traffic shape.
    await asyncio.gather(*write_tasks, *read_tasks)

    async with async_session() as session:
        for project_id in project_ids:
            project = await session.get(Project, project_id)
            ledger_sum, ledger_count = (
                await session.execute(
                    select(func.coalesce(func.sum(Bid.amount_paise), 0), func.count(Bid.id)).where(
                        Bid.project_id == project_id
                    )
                )
            ).one()

            assert ledger_count == BIDDERS_PER_PROJECT
            assert ledger_sum == BIDDERS_PER_PROJECT * BID_AMOUNT_PAISE
            assert project.cached_total_paise == ledger_sum
            assert project.total_bid_count == BIDDERS_PER_PROJECT
