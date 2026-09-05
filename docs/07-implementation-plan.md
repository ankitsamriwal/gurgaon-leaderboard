# 07 — Phased Implementation Plan

Build in this order. Each phase has an explicit exit criterion — don't
move to the next phase until it's met. Give Claude Code one phase at a
time, with the relevant numbered doc(s) as context.

## Phase 0 — Scaffolding
- Repo structure: `/api`, `/frontend`, `/infra` (docker-compose for local
  Postgres + Redis).
- FastAPI app skeleton, Postgres connection, Alembic migrations set up
  from `01-database-schema.md`.
- **Exit criterion:** `docker-compose up` gives a running API with an
  empty schema migrated in, and `/health` returns 200.

## Phase 1 — Ledger & transaction correctness (the core risk)
- Implement `projects`, `bids`, `payment_intents`, `webhook_events`
  tables and the bid-acceptance transaction from doc 01.
- Write the load test described in doc 05 (concurrent "beat the leader"
  attempts) and get it passing against Postgres directly, **before**
  wiring up Razorpay at all — use a fake "settle this intent" internal
  endpoint for testing.
- **Exit criterion:** concurrent load test shows zero double-counted or
  lost bids, and `cached_total_paise` always matches
  `SUM(bids.amount_paise)` after any run.

## Phase 2 — Auth
- OTP request/verify, JWT issuance, refresh rotation.
- **Exit criterion:** a user can sign up and get a valid session token;
  expired/rotated tokens are rejected.

## Phase 3 — Razorpay integration
- Real Order creation, Checkout wiring, webhook endpoint with signature
  verification, idempotency per doc 03.
- Test entirely in Razorpay test mode first.
- **Exit criterion:** a real (test-mode) end-to-end payment results in
  exactly one `bids` row, and replaying the same webhook payload twice
  does not create a second row.

## Phase 4 — Project submission & moderation
- Submission form/API, RERA format validation, duplicate rejection,
  admin approve/reject queue.
- **Exit criterion:** a submitted project never appears on the public
  leaderboard until an admin approves it.

## Phase 5 — Leaderboard & real-time frontend
- React app: leaderboard page, project detail, bid modal, WebSocket
  wiring per doc 04.
- **Exit criterion:** a settled webhook-verified bid updates the
  leaderboard for all connected clients within a few seconds, without
  a page refresh.

## Phase 6 — Admin panel & reconciliation
- Admin UI for moderation, RERA verification, refund handling.
- Nightly reconciliation job per doc 03.
- **Exit criterion:** intentionally desyncing a project's cached total
  from its ledger (in a test environment) gets caught and reported by
  the reconciliation job.

## Phase 7 — Security & anti-fraud pass
- Rate limiting, CAPTCHA on public forms, audit logging review,
  wash-trading flagging queries for the admin panel.
- **Exit criterion:** rate limits verified with a script that
  intentionally exceeds each limit and confirms a 429.

## Phase 8 — Legal/trust UI + compliance
- Disclaimers, verified-listing badges, dispute/takedown flow, privacy
  notice, data export/delete admin action.
- **Exit criterion:** legal review sign-off obtained (external — not a
  code deliverable, but block public launch on it).

## Phase 9 — Load testing & launch readiness
- Full staging load test against Razorpay test mode mirroring expected
  launch traffic.
- Backups configured and a restore drill actually performed once.
- Monitoring/alerting (error tracking, uptime, reconciliation alerts)
  verified to actually fire.
- **Exit criterion:** a simulated incident (e.g. kill the API pod mid
  -transaction) leaves the ledger consistent on restart, and alerts fire
  as expected.

## Explicit non-goals for this build (revisit post-launch)

- Multi-city support
- Automated RERA registry API integration (manual verification is the
  v1 answer)
- Native mobile apps
- Multi-currency / non-Razorpay payment rails
