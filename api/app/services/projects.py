import json
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Bid, LeadershipLog, Project
from app.redis_client import redis_client
from app.validators import is_valid_rera_number_format

LEADERBOARD_CACHE_KEY = "leaderboard:v1"
LEADERBOARD_CACHE_TTL_SECONDS = 7
LEADERBOARD_WS_CHANNEL = "leaderboard:updates"


def _error(status_code: int, code: str, message: str):
    raise HTTPException(status_code=status_code, detail={"error": {"code": code, "message": message}})


async def create_project(
    session: AsyncSession,
    *,
    submitted_by: uuid.UUID,
    name: str,
    developer_name: str,
    locality: str,
    rera_number: str,
    project_url: str | None,
) -> Project:
    if not is_valid_rera_number_format(rera_number):
        _error(400, "RERA_INVALID_FORMAT", "rera_number does not match the expected Haryana RERA format")

    project = Project(
        name=name,
        developer_name=developer_name,
        locality=locality,
        rera_number=rera_number,
        project_url=project_url,
        submitted_by=submitted_by,
        status="pending_review",
    )
    session.add(project)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        _error(409, "RERA_DUPLICATE", "a non-rejected project with this rera_number already exists")

    await session.refresh(project)
    return project


async def get_leaderboard(session: AsyncSession, *, use_cache: bool = True) -> dict:
    if use_cache:
        cached = await redis_client.get(LEADERBOARD_CACHE_KEY)
        if cached is not None:
            return json.loads(cached)

    result = await _compute_leaderboard(session)

    if use_cache:
        await redis_client.set(LEADERBOARD_CACHE_KEY, json.dumps(result), ex=LEADERBOARD_CACHE_TTL_SECONDS)

    return result


async def publish_leaderboard_update(session: AsyncSession) -> dict:
    """Recompute the leaderboard, refresh the read cache, and push it to
    `/ws/leaderboard` subscribers (docs/02: "server pushes a diff whenever
    the top-5 ordering or any project's total changes"). Called by whatever
    just landed a real bid (the webhook handler, the mock-payment endpoint)
    — not by app/services/bids.py itself, to keep that already
    load-tested transaction untouched.
    """
    payload = await _compute_leaderboard(session)
    encoded = json.dumps(payload)
    await redis_client.set(LEADERBOARD_CACHE_KEY, encoded, ex=LEADERBOARD_CACHE_TTL_SECONDS)
    await redis_client.publish(LEADERBOARD_WS_CHANNEL, encoded)
    return payload


async def _compute_leaderboard(session: AsyncSession) -> dict:
    rankings_rows = (
        await session.execute(
            select(Project)
            .where(Project.status == "live")
            .order_by(Project.cached_total_paise.desc(), Project.id.asc())
            .limit(5)
        )
    ).scalars().all()

    rankings = [
        {
            "rank": i + 1,
            "project_id": str(p.id),
            "name": p.name,
            "developer_name": p.developer_name,
            "locality": p.locality,
            "total_paise": p.cached_total_paise,
            "bid_count": p.total_bid_count,
        }
        for i, p in enumerate(rankings_rows)
    ]

    leader = None
    open_leadership = (
        await session.execute(
            select(LeadershipLog).where(LeadershipLog.lost_leader_at.is_(None)).order_by(
                LeadershipLog.became_leader_at.desc()
            ).limit(1)
        )
    ).scalar_one_or_none()
    if open_leadership is not None:
        leader = {
            "project_id": str(open_leadership.project_id),
            "leader_since": open_leadership.became_leader_at.isoformat(),
        }

    daily_topper = None
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    row = (
        await session.execute(
            select(Bid.project_id, func.sum(Bid.amount_paise).label("total"))
            .where(Bid.created_at > since, Bid.reversed.is_(False))
            .group_by(Bid.project_id)
            .order_by(func.sum(Bid.amount_paise).desc())
            .limit(1)
        )
    ).first()
    if row is not None:
        daily_topper = {"project_id": str(row.project_id), "last_24h_paise": int(row.total)}

    return {"leader": leader, "daily_topper": daily_topper, "rankings": rankings}


async def get_project_detail(session: AsyncSession, *, project_id: uuid.UUID, page: int, page_size: int) -> dict:
    project = await session.get(Project, project_id)
    if project is None or project.status != "live":
        _error(404, "PROJECT_NOT_LIVE", "project not found or not public")

    page_size = min(max(page_size, 1), 50)
    offset = max(page, 0) * page_size

    bids = (
        await session.execute(
            select(Bid)
            .where(Bid.project_id == project_id, Bid.reversed.is_(False))
            .order_by(Bid.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
    ).scalars().all()

    return {
        "id": str(project.id),
        "name": project.name,
        "developer_name": project.developer_name,
        "locality": project.locality,
        "rera_number": project.rera_number,
        "rera_verified": project.rera_verified,
        "project_url": project.project_url,
        "is_verified_developer_listing": project.claimed_by is not None,
        "total_paise": project.cached_total_paise,
        "bid_count": project.total_bid_count,
        "bids": {
            "page": page,
            "page_size": page_size,
            "items": [
                {
                    "id": str(b.id),
                    # bidder_label is display-only, never identity (docs/01) —
                    # user_id is never exposed on this public endpoint.
                    "bidder_label": b.bidder_label,
                    "amount_paise": b.amount_paise,
                    "created_at": b.created_at.isoformat(),
                }
                for b in bids
            ],
        },
    }
