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

Everything after Phase 2 (Razorpay, frontend, admin panel, security
hardening, legal/compliance UI) is **not yet built** — follow the phased
plan and do not skip ahead, per the non-negotiables in `docs/00-overview.md`.

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

## Layout

```
api/        FastAPI service, SQLAlchemy models, Alembic migrations
frontend/   React + Vite + TypeScript app (Phase 5+, not yet scaffolded)
infra/      docker-compose for local Postgres + Redis + API
docs/       The full spec (source of truth — do not reimplement from memory)
```
