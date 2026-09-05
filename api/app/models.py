"""SQLAlchemy models mirroring docs/01-database-schema.md exactly.

Do not add mutable "current total" columns beyond the documented rebuildable
caches (`cached_total_paise`, `total_bid_count`) — rank is always derived
from the `bids` ledger. See docs/01-database-schema.md for the rationale and
the canonical DDL/transaction this schema must match.
"""

import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    phone: Mapped[str | None] = mapped_column(Text, unique=True)
    email: Mapped[str | None] = mapped_column(Text, unique=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    role: Mapped[str] = mapped_column(Text, nullable=False, default="user")
    created_at: Mapped[object] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

    __table_args__ = (CheckConstraint("role IN ('user','developer','admin')", name="ck_users_role"),)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    name: Mapped[str] = mapped_column(Text, nullable=False)
    developer_name: Mapped[str] = mapped_column(Text, nullable=False)
    locality: Mapped[str] = mapped_column(Text, nullable=False)
    rera_number: Mapped[str] = mapped_column(Text, nullable=False)
    rera_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rera_verified_at: Mapped[object | None] = mapped_column(TIMESTAMP(timezone=True))
    project_url: Mapped[str | None] = mapped_column(Text)
    submitted_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    claimed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending_review")
    cached_total_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_bid_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[object] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_review','live','rejected','suspended')", name="ck_projects_status"
        ),
        Index("ix_projects_status_total", "status", cached_total_paise.desc()),
    )


class PaymentIntent(Base):
    __tablename__ = "payment_intents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    razorpay_order_id: Mapped[str | None] = mapped_column(Text, unique=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="created")
    created_at: Mapped[object] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("amount_paise > 0", name="ck_payment_intents_amount_positive"),
        CheckConstraint(
            "status IN ('created','order_created','pending_webhook','verified','failed','expired')",
            name="ck_payment_intents_status",
        ),
        Index("ix_intents_status", "status"),
    )


class Bid(Base):
    __tablename__ = "bids"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    payment_intent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payment_intents.id"), nullable=False, unique=True
    )
    razorpay_payment_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    bidder_label: Mapped[str | None] = mapped_column(Text)
    is_mock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reversed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reversed_at: Mapped[object | None] = mapped_column(TIMESTAMP(timezone=True))
    reversal_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[object] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("amount_paise > 0", name="ck_bids_amount_positive"),
        Index("ix_bids_project_created", "project_id", created_at.desc()),
        Index("ix_bids_created_at", created_at.desc()),
    )


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    razorpay_event_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    signature_valid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    processed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    processed_at: Mapped[object | None] = mapped_column(TIMESTAMP(timezone=True))
    received_at: Mapped[object] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())


class AdminAction(Base):
    __tablename__ = "admin_actions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    admin_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    action_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_table: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[object] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())


class LeadershipLog(Base):
    __tablename__ = "leadership_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    became_leader_at: Mapped[object] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    lost_leader_at: Mapped[object | None] = mapped_column(TIMESTAMP(timezone=True))
