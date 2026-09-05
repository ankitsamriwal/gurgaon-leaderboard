# Gurgaon Leaderboard — Production Rebuild Spec

This folder is a complete rebuild spec for the "Gurgaon Leaderboard" project
(pay-to-rank real-estate leaderboard, originally a Flask/SQLite MVP). It is
written to be handed directly to Claude Code as the source of truth for a
ground-up rebuild.

## How to use this with Claude Code

1. Drop this folder into the root of a new empty repo (or alongside the old
   MVP repo for reference — do not reuse its code).
2. Start with `07-implementation-plan.md` — it defines build order and
   phase gates. Work phase by phase; don't let Claude Code jump ahead to
   frontend polish before the ledger/transaction logic in Phase 1 is tested.
3. Each of the numbered docs is scoped to one concern and can be handed to
   Claude Code as the context for that phase's session:
   - `00-overview.md` — architecture, stack, non-negotiables
   - `01-database-schema.md` — Postgres schema, DDL, transaction/locking rules
   - `02-api-spec.md` — REST endpoints, request/response contracts, auth
   - `03-payment-integration.md` — Razorpay webhook flow, idempotency, reconciliation
   - `04-frontend-spec.md` — pages, components, state, real-time updates
   - `05-security-anti-fraud.md` — auth, rate limiting, RERA verification, moderation
   - `06-legal-compliance.md` — ToS/disclaimer/DPDP requirements to build against
   - `07-implementation-plan.md` — phased delivery order with exit criteria per phase

4. Treat `01-database-schema.md` and `03-payment-integration.md` as
   load-bearing — the money-correctness logic (idempotency, row locking,
   webhook-only settlement) must not be simplified away for speed.

## What is explicitly NOT in scope for v1

- Multi-city expansion (Gurgaon only)
- Native mobile apps
- Automated RERA registry scraping (v1 uses manual admin verification against
  the public Haryana RERA portal; automation is a fast-follow, not a blocker)
