"""The bid-acceptance transaction from docs/01-database-schema.md.

This must only ever be called from a verified payment source — the Razorpay
webhook handler in production, or the internal mock-settle endpoint in
non-prod builds (see app/routers/internal.py). Never call this from a
client-facing "checkout success" callback: client-side success is a UX hint
only, per docs/00-overview.md non-negotiable #2.
"""

import uuid
from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Bid, LeadershipLog, PaymentIntent, Project

# Arbitrary fixed key for pg_advisory_xact_lock — see _update_leadership_log.
_LEADERSHIP_LOG_ADVISORY_LOCK_KEY = 72700100


class BidResult:
    def __init__(self, bid: Bid, project: Project, already_settled: bool):
        self.bid = bid
        self.project = project
        self.already_settled = already_settled


async def accept_bid(
    session: AsyncSession,
    *,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    amount_paise: int,
    idempotency_key: str,
    razorpay_payment_id_for: Callable[[PaymentIntent], str],
    bidder_label: str | None = None,
    is_mock: bool = False,
) -> BidResult:
    """Get-or-create the payment_intent and settle it, per docs/01 + docs/03.

    Locks the target project row FIRST, before creating or touching any row
    that foreign-keys to it (payment_intents, bids). Locking a row only
    *after* other rows already hold a weaker FK-share lock on it is a
    lock-upgrade deadlock under concurrent load — every writer must acquire
    locks in the same order (docs/01-database-schema.md's deadlock-avoidance
    rule) — so this function, not the caller, owns intent creation.
    """
    project = (
        await session.execute(select(Project).where(Project.id == project_id).with_for_update())
    ).scalar_one()

    intent = (
        await session.execute(select(PaymentIntent).where(PaymentIntent.idempotency_key == idempotency_key))
    ).scalar_one_or_none()

    if intent is None:
        intent = PaymentIntent(
            project_id=project_id,
            user_id=user_id,
            amount_paise=amount_paise,
            idempotency_key=idempotency_key,
            status="order_created",
        )
        session.add(intent)
        try:
            await session.flush()
        except IntegrityError:
            # A different project's intent raced us to the same
            # idempotency_key (client bug) — DB constraint is the backstop.
            await session.rollback()
            raise

    existing = await _find_bid_for_intent(session, intent.id)
    if existing is not None:
        await session.commit()
        return BidResult(existing, project, already_settled=True)

    razorpay_payment_id = razorpay_payment_id_for(intent)

    bid = Bid(
        project_id=project.id,
        user_id=intent.user_id,
        payment_intent_id=intent.id,
        razorpay_payment_id=razorpay_payment_id,
        amount_paise=intent.amount_paise,
        bidder_label=bidder_label,
        is_mock=is_mock,
    )
    session.add(bid)

    project.cached_total_paise += intent.amount_paise
    project.total_bid_count += 1
    project.version += 1
    project.updated_at = datetime.now(timezone.utc)

    intent.status = "verified"
    intent.updated_at = datetime.now(timezone.utc)

    await _update_leadership_log(session)

    try:
        await session.commit()
    except IntegrityError:
        # Another concurrent call already settled this exact payment_intent_id
        # or razorpay_payment_id (bids.payment_intent_id / razorpay_payment_id
        # are UNIQUE) — the project row lock only serializes writers to the
        # *same project*, so this is the last line of defense for retries
        # racing on the very same intent. Never double-count; return what
        # actually landed.
        await session.rollback()
        existing = await _find_bid_for_intent(session, intent.id)
        if existing is None:
            raise
        project = await session.get(Project, existing.project_id)
        return BidResult(existing, project, already_settled=True)

    await session.refresh(bid)
    await session.refresh(project)
    return BidResult(bid, project, already_settled=False)


async def _find_bid_for_intent(session: AsyncSession, payment_intent_id: uuid.UUID) -> Bid | None:
    return (
        await session.execute(select(Bid).where(Bid.payment_intent_id == payment_intent_id))
    ).scalar_one_or_none()


async def _update_leadership_log(session: AsyncSession) -> None:
    """Keep leadership_log in sync with the #1 live project.

    Recomputes who the *global* current leader is and compares against the
    open leadership_log row — not scoped to whichever project the caller
    just touched. That distinction only matters once totals can go down
    (reverse_bid): a project's own bid increasing can only ever help or
    hold its own rank, never hand the lead to some third, untouched
    project, so checking "did I become leader" was sufficient for
    accept_bid alone. A reversal can knock the *current* leader out of
    first without whatever project it's compared against being the new
    one, so the general form is needed once refunds exist too.

    Only the target project's row is locked by callers (per doc 01:
    locking more than one project row is normally unnecessary). This
    function itself can end up inserting a leadership_log row that
    FK-references a *different* project than whichever one the caller
    locked (whenever leadership just changed to some other project) —
    under concurrent load across many projects, two transactions doing
    that for two different (unlocked, from their own perspective) leader
    projects can deadlock on each other's FK-share locks, per doc 01's
    "acquire locks in a fixed order" rule. leadership_log churn is rare
    (only on an actual leadership change) and not money-correctness
    load-bearing, so instead of a fixed lock *order* this just serializes
    every call through one advisory lock — simpler, and cheap given how
    infrequently leadership actually changes.
    """
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _LEADERSHIP_LOG_ADVISORY_LOCK_KEY})

    current_leader_id = (
        await session.execute(
            select(Project.id)
            .where(Project.status == "live")
            .order_by(Project.cached_total_paise.desc(), Project.id.asc())
            .limit(1)
        )
    ).scalar_one_or_none()

    open_row = (
        await session.execute(
            select(LeadershipLog)
            .where(LeadershipLog.lost_leader_at.is_(None))
            .order_by(LeadershipLog.became_leader_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if current_leader_id is None:
        if open_row is not None:
            open_row.lost_leader_at = datetime.now(timezone.utc)
        return

    if open_row is not None and open_row.project_id == current_leader_id:
        return

    now = datetime.now(timezone.utc)
    if open_row is not None:
        open_row.lost_leader_at = now
    session.add(LeadershipLog(project_id=current_leader_id, became_leader_at=now))


async def reverse_bid(session: AsyncSession, *, bid_id: uuid.UUID, reason: str | None) -> Bid:
    """Refund/chargeback handling (docs/02, docs/03): marks the bid
    reversed and recalculates the project's cached_total_paise inside a
    transaction. docs/03: no retroactive rewrite of leadership_log history
    — only current totals and future leadership are affected, which
    _update_leadership_log already guarantees (it only ever opens/closes
    the *current* open row, never edits closed historical ones).
    """
    bid = await session.get(Bid, bid_id)
    if bid is None:
        raise ValueError(f"unknown bid {bid_id}")
    if bid.reversed:
        return bid  # idempotent — already reversed, nothing to redo

    project = (
        await session.execute(select(Project).where(Project.id == bid.project_id).with_for_update())
    ).scalar_one()

    bid.reversed = True
    bid.reversed_at = datetime.now(timezone.utc)
    bid.reversal_reason = reason

    project.cached_total_paise -= bid.amount_paise
    project.total_bid_count -= 1
    project.version += 1
    project.updated_at = datetime.now(timezone.utc)

    await _update_leadership_log(session)

    await session.commit()
    await session.refresh(bid)
    return bid
