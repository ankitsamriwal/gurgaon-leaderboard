# 01 — Database Schema (PostgreSQL)

## Design principles

- Bids are **append-only**. Never `UPDATE` a running total column and treat
  it as truth — always derive current total as `SUM(amount)` over
  `settled` bids, or maintain a cached counter that is *rebuildable* from
  the ledger at any time (cache, not source of truth).
- Every state-changing money operation happens inside a single DB
  transaction using `SELECT ... FOR UPDATE` on the row(s) being compared,
  so the "must beat current leader by ≥ ₹1" check and the write are
  atomic.
- Foreign keys enforced; no orphaned bids/intents.
- All money stored as integer paise (₹1 = 100 paise) — never floats.

## Tables

### `users`
```sql
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone           TEXT UNIQUE,
    email           TEXT UNIQUE,
    display_name    TEXT NOT NULL,
    is_verified     BOOLEAN NOT NULL DEFAULT FALSE,
    role            TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user','developer','admin')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### `projects`
```sql
CREATE TABLE projects (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT NOT NULL,
    developer_name      TEXT NOT NULL,
    locality            TEXT NOT NULL,
    rera_number         TEXT NOT NULL,
    rera_verified       BOOLEAN NOT NULL DEFAULT FALSE,
    rera_verified_at    TIMESTAMPTZ,
    project_url         TEXT,
    submitted_by        UUID NOT NULL REFERENCES users(id),
    claimed_by          UUID REFERENCES users(id),  -- verified developer owner, nullable
    status              TEXT NOT NULL DEFAULT 'pending_review'
                          CHECK (status IN ('pending_review','live','rejected','suspended')),
    cached_total_paise  BIGINT NOT NULL DEFAULT 0,  -- derived cache, rebuildable from bids
    total_bid_count     INT NOT NULL DEFAULT 0,     -- derived cache
    version             INT NOT NULL DEFAULT 0,      -- optimistic lock guard, belt-and-suspenders alongside SELECT FOR UPDATE
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX ux_projects_rera_number ON projects(rera_number)
    WHERE status != 'rejected';  -- prevent duplicate live listings of same RERA project
CREATE INDEX ix_projects_status_total ON projects(status, cached_total_paise DESC);
```

### `payment_intents`
Created the moment a user clicks "pay" — before Razorpay order creation
completes. This is what lets you reconcile abandoned/failed checkouts.
```sql
CREATE TABLE payment_intents (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID NOT NULL REFERENCES projects(id),
    user_id             UUID NOT NULL REFERENCES users(id),
    amount_paise        BIGINT NOT NULL CHECK (amount_paise > 0),
    idempotency_key     TEXT NOT NULL UNIQUE,  -- client-generated, e.g. UUID per submit click
    razorpay_order_id   TEXT UNIQUE,
    status              TEXT NOT NULL DEFAULT 'created'
                          CHECK (status IN ('created','order_created','pending_webhook','verified','failed','expired')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_intents_status ON payment_intents(status);
```

### `bids`
The immutable ledger. One row per **settled** payment. Never updated after
insert except for `refunded_at` / `reversed`.
```sql
CREATE TABLE bids (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID NOT NULL REFERENCES projects(id),
    user_id             UUID NOT NULL REFERENCES users(id),
    payment_intent_id   UUID NOT NULL REFERENCES payment_intents(id) UNIQUE,
    razorpay_payment_id TEXT NOT NULL UNIQUE,
    amount_paise        BIGINT NOT NULL CHECK (amount_paise > 0),
    bidder_label        TEXT,               -- display-only, never identity
    is_mock             BOOLEAN NOT NULL DEFAULT FALSE,
    reversed            BOOLEAN NOT NULL DEFAULT FALSE,   -- true if refunded/charged back
    reversed_at         TIMESTAMPTZ,
    reversal_reason     TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_bids_project_created ON bids(project_id, created_at DESC);
CREATE INDEX ix_bids_created_at ON bids(created_at DESC);  -- for "daily topper" window queries
```

### `webhook_events`
Raw log of every Razorpay webhook received, for audit + replay safety.
```sql
CREATE TABLE webhook_events (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    razorpay_event_id   TEXT NOT NULL UNIQUE,   -- Razorpay's own event id, dedupe key
    event_type          TEXT NOT NULL,
    payload             JSONB NOT NULL,
    signature_valid     BOOLEAN NOT NULL,
    processed           BOOLEAN NOT NULL DEFAULT FALSE,
    processed_at        TIMESTAMPTZ,
    received_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### `admin_actions`
Audit trail for moderation/refund decisions.
```sql
CREATE TABLE admin_actions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    admin_user_id   UUID NOT NULL REFERENCES users(id),
    action_type     TEXT NOT NULL,   -- e.g. 'approve_project','reject_project','verify_rera','refund_bid'
    target_table    TEXT NOT NULL,
    target_id       UUID NOT NULL,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## The critical transaction: accepting a new bid

This is the sequence that must run inside one DB transaction, triggered
**only** by a verified webhook event (never by the client callback):

```sql
BEGIN;

-- Lock the target project row so no concurrent bid can read a stale total
SELECT id, cached_total_paise, version
  FROM projects
 WHERE id = :project_id
 FOR UPDATE;

-- App-layer check (only needed if this bid is meant to unseat #1 —
-- ordinary bids just add to a project's own total and re-sort naturally):
--   IF this bid's resulting total must exceed current #1's total,
--   re-read current #1 with FOR UPDATE too, in a fixed lock order
--   (e.g. always lock projects by id ASC) to avoid deadlocks.

INSERT INTO bids (project_id, user_id, payment_intent_id, razorpay_payment_id, amount_paise, bidder_label, is_mock)
VALUES (:project_id, :user_id, :intent_id, :rzp_payment_id, :amount_paise, :label, :is_mock);

UPDATE projects
   SET cached_total_paise = cached_total_paise + :amount_paise,
       total_bid_count = total_bid_count + 1,
       version = version + 1,
       updated_at = now()
 WHERE id = :project_id;

UPDATE payment_intents SET status = 'verified', updated_at = now()
 WHERE id = :intent_id;

COMMIT;
```

**Deadlock avoidance rule:** if a single logical operation ever needs to
lock more than one project row (it normally doesn't — bids only touch
their own project), always acquire locks in a fixed order (e.g. sorted by
`id`) to prevent circular waits.

**Rebuild/repair:** `cached_total_paise` and `total_bid_count` must be
fully reconstructable at any time via:
```sql
SELECT project_id, SUM(amount_paise), COUNT(*)
  FROM bids
 WHERE reversed = FALSE
 GROUP BY project_id;
```
Run this as a nightly consistency check job — any drift between the cache
and this query is a bug to page someone about, not silently correct in
prod without alerting.

## Derived views for the leaderboard API

```sql
-- Overall leaderboard (top 5)
SELECT id, name, developer_name, locality, cached_total_paise, total_bid_count
  FROM projects
 WHERE status = 'live'
 ORDER BY cached_total_paise DESC
 LIMIT 5;

-- Daily topper (highest single project total paid in last 24h)
SELECT project_id, SUM(amount_paise) AS last_24h_paise
  FROM bids
 WHERE created_at > now() - INTERVAL '24 hours'
   AND reversed = FALSE
 GROUP BY project_id
 ORDER BY last_24h_paise DESC
 LIMIT 1;

-- "Leader for X days/hours" — track via a separate lightweight table or
-- compute from bids history: find the earliest created_at after which
-- the current #1's cached_total_paise has continuously exceeded every
-- other project's. Simplest robust approach: maintain a
-- `leadership_log(project_id, became_leader_at, lost_leader_at)` table,
-- appended to whenever the #1 changes (in the same transaction above).
```

### `leadership_log` (add-on table for the timer feature)
```sql
CREATE TABLE leadership_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES projects(id),
    became_leader_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    lost_leader_at   TIMESTAMPTZ
);
```
On every bid transaction, after updating totals, check if the #1 project
changed; if so, close out the previous leader's open row
(`lost_leader_at = now()`) and insert a new row for the new leader.
