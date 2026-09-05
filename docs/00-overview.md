# 00 — Overview & Architecture

## Product recap

Real-estate projects compete for leaderboard position based on cumulative ₹
paid against them. To take #1, a challenger must have a running total at
least ₹1 higher than the current leader's. Top 5 shown on the public ladder.

## Non-negotiables for v1 (do not simplify these away)

1. **Money correctness over feature speed.** Every bid is an immutable
   ledger entry. Leaderboard rank is always derived, never stored as a
   mutable "current total" field that can drift from the ledger.
2. **Webhook is the only source of truth for "paid."** Client-side checkout
   success is a UX hint only — it never updates rank.
3. **No anonymous project submission.** Every project has a verified
   submitter identity before it can go live.
4. **Admin moderation gate.** No project appears publicly until approved.
5. **Idempotency everywhere money moves.** Retries must never double-count.

## Stack

| Layer | Choice | Why |
|---|---|---|
| API | FastAPI (Python 3.12) | async, typed, easy webhook handling, team already knows Python |
| DB | PostgreSQL 16 | row-level locking (`SELECT ... FOR UPDATE`), real transactions — SQLite cannot safely serialize concurrent bid writes |
| Cache / rate limit | Redis | leaderboard read cache, per-IP/user rate limiting, idempotency key store |
| Payments | Razorpay (Orders API + Webhooks) | matches original MVP, supports test mode |
| Auth | Email or phone OTP (e.g. via MSG91/Twilio + JWT sessions) | no anonymous bidding/submission |
| Frontend | React + Vite + TypeScript | testable state, needed for real-time rank updates |
| Real-time | WebSocket (or polling fallback every 5–10s) | live "outbid" feel is core to the mechanic |
| Admin panel | Separate authenticated route/app (or Django admin-style panel bolted onto FastAPI) | project moderation, refund handling, RERA verification queue |
| Hosting | Any container platform (Render/Railway/Fly/AWS ECS) | containerize API + worker + frontend separately |
| Background jobs | Celery or RQ + Redis, or APScheduler for simple cron | webhook retry sweep, nightly reconciliation, RERA re-checks |

## Service boundaries

```
Browser (React SPA)
   │
   ├── REST/WebSocket ──▶ API service (FastAPI)
   │                         │
   │                         ├── Postgres (source of truth)
   │                         ├── Redis (cache, rate limit, idempotency)
   │                         └── Razorpay Orders API (create order)
   │
Razorpay ── webhook (signed) ──▶ Webhook service (separate route/process,
                                   same codebase is fine, but treat as a
                                   distinct trust boundary — verify signature
                                   before touching DB, log every payload)
                                         │
                                         └── Postgres (writes bid on verified event)

Nightly job ──▶ Reconciliation worker ──▶ compares Razorpay settlement
                                            report vs. bids ledger, alerts
                                            on mismatch
```

## Environments

- `local` — Razorpay test mode, seeded demo data, mock-mode fully disabled
  by build flag (not just env var) outside `local`/`staging`.
- `staging` — Razorpay test mode, mirrors prod config, used for load
  testing the bid-placement endpoint.
- `production` — Razorpay live mode, mock mode compiled out.

## Key risk this spec is designed around

Two users submitting a "beat the leader by ₹1" payment within milliseconds
of each other. The schema and API spec (docs 01–02) exist primarily to make
this scenario safe and deterministic rather than a race.
