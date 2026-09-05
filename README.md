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

Everything after Phase 0 (ledger transaction logic, auth, Razorpay, frontend,
admin panel, security hardening, legal/compliance UI) is **not yet built** —
follow the phased plan and do not skip ahead, per the non-negotiables in
`docs/00-overview.md`.

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

## Layout

```
api/        FastAPI service, SQLAlchemy models, Alembic migrations
frontend/   React + Vite + TypeScript app (Phase 5+, not yet scaffolded)
infra/      docker-compose for local Postgres + Redis + API
docs/       The full spec (source of truth — do not reimplement from memory)
```
