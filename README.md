# Gurgaon Leaderboard

Production rebuild of the pay-to-rank real-estate leaderboard. Full spec lives
in [`docs/`](docs/) — start with `docs/07-implementation-plan.md` for build
order and phase gates.

## Status

**Phase 0 — Scaffolding** (see `docs/07-implementation-plan.md`)

- [x] Repo structure: `api/`, `frontend/`, `infra/`
- [x] FastAPI app skeleton + `/health`
- [x] Postgres connection (async SQLAlchemy + asyncpg)
- [x] Alembic migrations set up from `docs/01-database-schema.md`
- [x] Verified end-to-end against a real Postgres 16 + Redis: `alembic
      upgrade head` creates all 7 tables from the schema doc, and the API
      serves `GET /health` → `200 {"status":"ok"}`. Verified directly (pip
      install + local Postgres/Redis) rather than via `docker compose up`,
      since the sandbox this was built in has no outbound access to Docker
      Hub's image registry — the `Dockerfile`/`docker-compose.yml` should be
      re-verified with `docker compose up --build` the first time this runs
      somewhere with normal registry access.

**Phase 1 — Ledger & transaction correctness** (the core risk, per
`docs/07-implementation-plan.md`)

- [x] Bid-acceptance transaction (`app/services/bids.py`) implementing the
      `SELECT ... FOR UPDATE` flow from `docs/01-database-schema.md`,
      get-or-create-by-idempotency-key semantics from `docs/03`, and
      `leadership_log` maintenance.
- [x] Internal mock-settle endpoints (`app/routers/internal.py`,
      `/internal/test/*`) standing in for the Razorpay webhook, so the
      ledger can be load-tested before Phase 3 wires up real payments.
      Registered only when `ENVIRONMENT != production`, checked once at
      app-factory time — confirmed excluded from a production-mode app
      (no `/internal/*` routes registered).
- [x] Concurrent load test (`tests/load/test_concurrent_bids.py`) per
      `docs/05-security-anti-fraud.md`'s release-gate: 100 concurrent bids
      against the same project. **Exit criterion met** — verified against
      real Postgres, 5 consecutive runs, zero double-counted or lost bids,
      `cached_total_paise` always equals `SUM(bids.amount_paise)`.
      A second test confirms a double-tapped idempotency key never
      double-counts even when settled concurrently.
- **Real bug caught and fixed by this test**: the first implementation
  created the `payment_intents` row (which takes an implicit `FOR KEY
  SHARE` lock on the referenced project row via its foreign key) *before*
  locking the project row `FOR UPDATE`. Under concurrent load this is a
  classic lock-upgrade deadlock — every concurrent transaction holds the
  weak lock and waits to upgrade to the strong one. Fixed by always
  acquiring the project's `FOR UPDATE` lock first, before creating or
  touching any row that foreign-keys to it — see the docstring on
  `accept_bid()` in `app/services/bids.py`.

**Phase 2 — Auth** (`docs/07-implementation-plan.md`)

- [x] OTP request/verify (`app/routers/auth.py`, `app/services/auth.py`),
      JWT access tokens, refresh-token rotation with reuse detection per
      `docs/05-security-anti-fraud.md`.
- [x] `otp_requests` and `refresh_tokens` tables added (migration `0002`) —
      not in `docs/01-database-schema.md`, which only covers the money
      tables; these support the auth design from `docs/00`/`docs/05`.
- [x] OTP delivery is pluggable (`app/services/otp_provider.py`); the only
      implementation right now logs the code and — **only outside
      production** — echoes it in the API response as `debug_otp`, since
      there's no real SMS/email account (MSG91/Twilio, per `docs/00`) to
      wire up. `get_otp_provider()` raises at startup if
      `ENVIRONMENT=production` and no real provider has been substituted —
      it fails loudly rather than silently not sending OTPs in prod.
- [x] Rate limiting on `/auth/otp/request` (5/hour per phone, per
      `docs/05`'s table) — the full endpoint-by-endpoint sweep is Phase 7,
      but this one's rate limit is part of the endpoint's own contract.
- [x] **Exit criterion met**, verified against real Postgres + Redis: a
      user signs up via OTP and gets a valid access+refresh token pair;
      an expired OTP is rejected (`OTP_EXPIRED`); a rotated refresh token
      is rejected on reuse (`REFRESH_REUSED`) and revokes its *entire*
      session chain, not just itself; logout revokes the session
      (`REFRESH_REVOKED`).
- **Known gap, by design**: no real OTP provider or SMS/email account
  exists for this build. Swap `LogOtpProvider` in
  `app/services/otp_provider.py` for a real MSG91/Twilio implementation
  before production — everything else (hashing, expiry, attempt limits,
  rate limiting) is provider-agnostic and already in place.

**Phase 3 — Razorpay integration** (`docs/07-implementation-plan.md`)

- [x] `POST /payments/intent` (`app/routers/payments.py`) — auth required,
      idempotent by `idempotency_key`, creates a real Razorpay Order via
      `app/services/razorpay_client.py`.
- [x] `POST /webhooks/razorpay` (`app/routers/webhooks.py`) — no user
      auth, HMAC-SHA256 signature verification over the raw request body
      (docs/03's reference implementation, byte-for-byte), dedup by
      `razorpay_event_id` against `webhook_events`, amount-match check
      against the intent, then settles through the *same* `accept_bid()`
      transaction Phase 1's load test already proved correct under
      concurrency.
- [x] `POST /payments/mock` — demo-only payment bypass from `docs/02`,
      auth required, registered only outside production (verified: absent
      from a production-mode app's routes).
- [x] **Exit criterion met**: end-to-end (intent → webhook) settles
      exactly one `bids` row; replaying the identical webhook payload
      returns `already_processed` and does not duplicate; an invalid
      signature is rejected and logged to `webhook_events` regardless; an
      amount mismatch between the webhook and the intent inserts no bid.
- **Known gap, by design**: no real Razorpay account/test-mode keys exist
  for this build (`RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET` are empty by
  default and `get_razorpay_client()` refuses to run without them). Order
  creation is tested via FastAPI's standard `dependency_overrides`
  mechanism (a fake Orders API client) — real, unmodified code runs in
  production; only the HTTP call to Razorpay itself was substituted for
  testing. Everything downstream — idempotency, signature verification,
  amount checks, the ledger transaction — was exercised for real against
  Postgres, including a real HMAC signature computed with a test webhook
  secret. Set real test-mode keys and do one live checkout against
  Razorpay's test mode before trusting this in staging.
- **Also flagged, not fixed**: `docs/03`'s "flag to `admin_actions`" for
  an amount mismatch doesn't fit the schema as designed —
  `admin_actions.admin_user_id` is `NOT NULL` (it models actions an admin
  *took*, not system-detected anomalies with no admin actor). Currently
  just logs at ERROR level instead. Fixing this properly needs either a
  nullable `admin_user_id` or a dedicated alerts table — a schema decision
  for whoever owns `docs/01`, not something to improvise around silently.

**Phase 4 — Project submission & moderation** (`docs/07-implementation-plan.md`)

- [x] `POST /projects` — auth required, RERA format check, duplicate
      rejection (DB constraint backed), 3/day-per-user rate limit. Goes to
      `pending_review`.
- [x] `GET /projects/leaderboard` (Redis-cached, 7s TTL) and
      `GET /projects/{id}` (paginated bid history; bid rows expose
      `bidder_label` only, never `user_id`, per docs/01's "display-only,
      never identity"). Both **404 `PROJECT_NOT_LIVE` for anything not
      live** — the moderation gate isn't bypassable by guessing/knowing a
      project id, even for the submitter.
- [x] Admin queue (`app/routers/admin.py`, `role=admin` only):
      `GET /admin/projects/pending`, `approve`, `reject`, `verify-rera` —
      every action logged to `admin_actions`. Approve/reject invalidate
      the leaderboard cache immediately rather than waiting out its TTL.
- [x] `POST /projects/{id}/claim` + admin `approve`/`reject` — approving a
      claim sets `projects.claimed_by` and promotes the claimant to
      `role='developer'`.
- [x] **Exit criterion met**: verified against real Postgres — a
      newly-submitted project is invisible on the leaderboard and 404s on
      direct fetch until an admin approves it; rejecting keeps it off
      permanently; a non-admin gets 403 on admin routes.
- **Design call, not in the spec docs**: `docs/02` gates the claim
  endpoint to "developer role", but nothing in this build ever grants
  that role up front — there's no signup-as-a-developer flow. Filing a
  claim is open to any authenticated user; admin *approval* of the claim
  is what promotes them to `role='developer'`, not a precondition for
  filing.
- **Known gap**: RERA number format validation (`app/validators.py`) is a
  best-effort shape check based on the publicly known
  `RC/REP/HARERA/<zone>/...` convention — there's no access to the real
  Haryana RERA portal to confirm the exact pattern. It rejects obvious
  garbage, nothing more; `docs/05` is explicit that only manual admin
  verification is the real source of truth here, which is what
  `verify-rera` is for.
- **Known gap**: there's no admin bootstrap flow (how does the first
  admin account get created?). `app/routers/internal.py`'s
  `/internal/test/promote-role` is test-only and absent from production
  builds; a real deployment needs a manual DB action or a separate
  invite process — an operational decision, not an API design one.

**Phase 5 — Leaderboard & real-time frontend** (`docs/07-implementation-plan.md`)

- [x] React + Vite + TypeScript app (`frontend/`) per `docs/04-frontend-spec.md`:
      leaderboard, project detail + bid modal, submit form, OTP login,
      a minimal dashboard, and an admin moderation/claims UI. React Query
      for server state, Zustand for the auth session, no Redux.
- [x] `WS /ws/leaderboard` (`app/routers/ws.py`) — broadcasts via Redis
      pub/sub (not an in-process socket list), so it stays correct across
      multiple worker processes in production. Triggered by
      `publish_leaderboard_update()` after a real settlement (the webhook
      handler, the mock-payment endpoint) — Phase 1's already-tested
      `accept_bid()` transaction itself is untouched.
- [x] `BidModal` calls `POST /payments/intent` and opens real Razorpay
      Checkout only when both `window.Razorpay` and a configured
      `razorpay_key_id` are present (checked via a new `GET /payments/config`
      endpoint *before* attempting anything); otherwise it settles via
      `POST /payments/mock` directly. Never optimistically renders a new
      total before settlement confirms it (docs/04).
- [x] **Exit criterion met — verified in an actual browser, not just unit
      tests**: ran the full app end to end (Chromium via Playwright)
      against the real API, Postgres, and Redis: OTP login → submit a
      project → admin-approve it → place a bid → leaderboard updates.
      Opened **two separate browser tabs**, placed a bid from one, and
      watched the leaderboard update live in the other with no page
      refresh, over the real `/ws/leaderboard` socket.
- **Two real bugs this testing caught and fixed** (not merely observed —
  both are hard requirements this build now meets):
  1. **No CORS middleware at all.** Every cross-origin frontend call was
     silently blocked by the browser. Fixed with `CORSMiddleware`,
     configurable via `CORS_ALLOWED_ORIGINS` (defaults to the Vite dev
     origin).
  2. **The demo payment path was unreachable without real Razorpay
     credentials.** `POST /payments/mock` required an `intent_id` that
     could only come from `POST /payments/intent` — which hard-fails
     without configured Razorpay keys. That made the credential-free demo
     path impossible to reach in exactly the environment it exists for.
     Fixed by making `/payments/mock` fully self-contained (it settles
     directly via `accept_bid()`, same as the webhook) and adding
     `GET /payments/config` so the frontend decides which path to use
     upfront instead of discovering it by provoking a failure.
  3. **`daily_topper`'s Postgres `SUM()` returned a `Decimal`**, which
     isn't JSON-serializable — `GET /projects/leaderboard` and the WS push
     would have thrown a 500 the first time any project had a bid in the
     last 24h. Fixed by casting to `int`.
- **Known gap**: `/dashboard` is a stub — `docs/02-api-spec.md` has no "my
  submissions" or "my bids" endpoint to back the page `docs/04` describes.
  Flagged in the UI itself rather than faked.

**Phase 6 — Admin panel & reconciliation** (`docs/07-implementation-plan.md`)

- [x] `POST /admin/bids/{id}/reverse` (`app/services/bids.py`'s
      `reverse_bid()`) — refund/chargeback handling: marks the bid
      reversed, recalculates `cached_total_paise`/`total_bid_count` inside
      the same locked-project transaction pattern as `accept_bid()`, logs
      to `admin_actions`.
- [x] Nightly reconciliation (`app/services/reconciliation.py`,
      `reconciliation_reports` table, migration `0004`): recomputes every
      project's total from the ledger, diffs against the cache, **logs
      the mismatch before correcting it** (docs/03: "auto-correct only
      after the alert fires, never silently"), and stores a report row as
      the paper trail. `GET /admin/reconciliation/report` and an on-demand
      `POST /admin/reconciliation/run` (not in `docs/02` — the minimal way
      to make the job operable/testable without a scheduler) expose it.
      `api/scripts/run_reconciliation.py` is the entrypoint for a real
      cron/APScheduler job.
- [x] Frontend `ReconciliationPanel` (docs/04) added to the admin page,
      plus a bid-reversal form.
- [x] **Exit criterion met**: intentionally desyncing a project's cache
      via raw SQL gets caught and corrected by `/admin/reconciliation/run`,
      verified against real Postgres.
- **Real bug this phase's testing caught and fixed**: `_update_leadership_log`
  (from Phase 1) only checked whether the project whose bid had just been
  accepted was the new #1 — correct as long as totals only ever increase,
  since a project gaining money can never hand the lead to some other,
  untouched project. Reversal breaks that invariant: knocking the current
  leader down can make a *third, untouched* project the new #1, which the
  old check would miss entirely (leaving `leadership_log`'s "current
  leader" stuck on a project that no longer leads). Fixed by having it
  always recompute the true global leader rather than checking only the
  caller's project. Covered by a regression test with three projects.
- **Known gap, by design**: `docs/03`'s reconciliation job also cross-checks
  the ledger against Razorpay's own settlement report/payments API — not
  implemented, since no real Razorpay account exists for this build (same
  gap noted in Phase 3). What's implemented and tested is this build's
  actual release gate: ledger-vs-cache consistency.

**Phase 7 — Security & anti-fraud pass** (`docs/07-implementation-plan.md`)

- [x] Completed the `docs/05` rate-limit table: added the per-IP limits
      that were missing (10/hour on `/auth/otp/request`, 50/hour on
      `/payments/intent`) alongside the per-phone/per-user ones already
      in place since Phases 2/3.
- [x] CAPTCHA on `/submit` and `/auth/otp/request`
      (`app/services/captcha_provider.py`) — same pluggable,
      fail-loudly-without-real-credentials pattern as the OTP provider:
      `NoopCaptchaProvider` passes everything outside production;
      `get_captcha_provider()` refuses to run in production without a
      real `TURNSTILE_SECRET_KEY`. No real Cloudflare Turnstile/hCaptcha
      site key exists for this build, so there's no widget wired into the
      frontend forms yet — the backend contract (verify a `captcha_token`,
      `CAPTCHA_FAILED` error code, hard-fail in prod) is what's
      implemented and tested; adding the real widget is a frontend-only
      follow-up once real site/secret keys exist.
- [x] Audit logging reviewed: every admin write action
      (approve/reject/verify-rera/claim-approve/claim-reject/bid-reverse)
      already logs to `admin_actions` (Phases 4/6) — no gaps found.
- [x] Wash-trading flag queries (`app/services/anti_fraud.py`,
      `GET /admin/anti-fraud/flags`) — flags only, never auto-blocks, per
      docs/05: repeated same-user bidding on one project in a tight
      window, bid clusters from newly-created accounts, and bid-velocity
      spikes against a project's own trailing baseline.
- [x] **Exit criterion met**: a script exceeding each configured rate
      limit gets a 429 with `RATE_LIMITED`, verified against real
      Postgres + Redis for the OTP-per-IP, payments-intent-per-user, and
      (from earlier phases) OTP-per-phone and project-submission limits.
- **Known gap, by design**: `docs/05`'s "same payment method fingerprint"
  wash-trading signal needs card/method data only a real Razorpay account
  provides (same root cause as the Phase 3/6 Razorpay gaps) — not
  implemented. The three heuristics that use data this system actually
  has (repeated bidder, new-account clustering, velocity spike) are.

Everything after Phase 7 (legal/compliance UI, launch readiness) is **not
yet built** — follow the phased plan and do not skip ahead, per the
non-negotiables in `docs/00-overview.md`.

## Local development

```bash
cd infra
docker compose up --build
```

This starts Postgres 16, Redis, and the API (running Alembic migrations on
startup, then serving on `http://localhost:8000`). Check `GET /health`.

To run migrations manually against a running Postgres:

```bash
cd api
pip install -r requirements.txt
alembic upgrade head
```

To run the test suite (needs a running Postgres + Redis, e.g. via
`docker compose up postgres redis` or local installs):

```bash
cd api
pip install -r requirements-dev.txt
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/gurgaon_leaderboard \
REDIS_URL=redis://localhost:6379/0 \
ENVIRONMENT=local \
pytest
```

To run the frontend against a local API:

```bash
cd frontend
npm install
VITE_API_BASE_URL=http://localhost:8000 npm run dev
```

The API's `CORS_ALLOWED_ORIGINS` defaults to `http://localhost:5173` (Vite's
default port) so this works without extra config. Set a real
`RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET` on the API to exercise real Razorpay
Checkout from `BidModal`; without them it automatically falls back to the
`POST /payments/mock` demo path.

## Layout

```
api/        FastAPI service, SQLAlchemy models, Alembic migrations
frontend/   React + Vite + TypeScript app (docs/04)
infra/      docker-compose for local Postgres + Redis + API
docs/       The full spec (source of truth — do not reimplement from memory)
```
