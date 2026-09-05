"""Wash-trading / anti-fraud flagging queries (docs/05-security-anti-fraud.md).

These flag for admin review — they never auto-block, per docs/05. docs/05
also mentions "same payment method fingerprint" as a signal, which needs
data (card/method info) that only a real Razorpay account provides — not
available in this build (same gap as docs/03's settlement cross-check).
What's implemented uses only data this system actually has: same-user
repeated bidding, new-account clustering, and bid velocity spikes.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Bid, User

REPEATED_BIDDER_WINDOW_HOURS = 1
REPEATED_BIDDER_THRESHOLD = 3

NEW_ACCOUNT_WINDOW_HOURS = 1
NEW_ACCOUNT_AGE_HOURS = 24
NEW_ACCOUNT_THRESHOLD = 5

VELOCITY_BASELINE_DAYS = 7
VELOCITY_MULTIPLIER = 3
VELOCITY_MIN_ABSOLUTE = 5


async def repeated_bidder_flags(session: AsyncSession) -> list[dict]:
    """Same user placing several bids on the same project in a tight
    window — a proxy for "same funding source counter-bidding itself"
    (docs/05) since this build has no payment-method fingerprint data."""
    since = datetime.now(timezone.utc) - timedelta(hours=REPEATED_BIDDER_WINDOW_HOURS)
    rows = (
        await session.execute(
            select(Bid.user_id, Bid.project_id, func.count(Bid.id).label("bid_count"))
            .where(Bid.created_at > since, Bid.reversed.is_(False))
            .group_by(Bid.user_id, Bid.project_id)
            .having(func.count(Bid.id) >= REPEATED_BIDDER_THRESHOLD)
        )
    ).all()
    return [
        {"user_id": str(r.user_id), "project_id": str(r.project_id), "bid_count": r.bid_count} for r in rows
    ]


async def new_account_cluster_flags(session: AsyncSession) -> list[dict]:
    """Many bids from newly-created accounts hitting one project in a
    tight window (docs/05: "potential coordinated inflation")."""
    bid_since = datetime.now(timezone.utc) - timedelta(hours=NEW_ACCOUNT_WINDOW_HOURS)
    account_since = datetime.now(timezone.utc) - timedelta(hours=NEW_ACCOUNT_AGE_HOURS)
    rows = (
        await session.execute(
            select(Bid.project_id, func.count(Bid.id).label("new_account_bid_count"))
            .join(User, User.id == Bid.user_id)
            .where(Bid.created_at > bid_since, Bid.reversed.is_(False), User.created_at > account_since)
            .group_by(Bid.project_id)
            .having(func.count(Bid.id) >= NEW_ACCOUNT_THRESHOLD)
        )
    ).all()
    return [{"project_id": str(r.project_id), "new_account_bid_count": r.new_account_bid_count} for r in rows]


async def velocity_spike_flags(session: AsyncSession) -> list[dict]:
    """A project's last-hour bid volume far outside its own trailing
    baseline (docs/05: "flag for visibility, not automatic action — could
    be legitimate hype")."""
    now = datetime.now(timezone.utc)
    last_hour_since = now - timedelta(hours=1)
    baseline_since = now - timedelta(days=VELOCITY_BASELINE_DAYS)

    last_hour_rows = (
        await session.execute(
            select(Bid.project_id, func.count(Bid.id).label("count"))
            .where(Bid.created_at > last_hour_since, Bid.reversed.is_(False))
            .group_by(Bid.project_id)
        )
    ).all()

    baseline_rows = (
        await session.execute(
            select(Bid.project_id, func.count(Bid.id).label("count"))
            .where(
                Bid.created_at > baseline_since,
                Bid.created_at <= last_hour_since,
                Bid.reversed.is_(False),
            )
            .group_by(Bid.project_id)
        )
    ).all()
    baseline_hours = VELOCITY_BASELINE_DAYS * 24
    baseline_avg: dict[uuid.UUID, float] = {r.project_id: r.count / baseline_hours for r in baseline_rows}

    flags = []
    for row in last_hour_rows:
        if row.count < VELOCITY_MIN_ABSOLUTE:
            continue
        avg = baseline_avg.get(row.project_id, 0.0)
        if avg == 0.0 or row.count > avg * VELOCITY_MULTIPLIER:
            flags.append(
                {
                    "project_id": str(row.project_id),
                    "last_hour_bid_count": row.count,
                    "baseline_hourly_average": round(avg, 2),
                }
            )
    return flags


async def compute_anti_fraud_flags(session: AsyncSession) -> dict:
    return {
        "repeated_bidder_flags": await repeated_bidder_flags(session),
        "new_account_cluster_flags": await new_account_cluster_flags(session),
        "velocity_spike_flags": await velocity_spike_flags(session),
    }
