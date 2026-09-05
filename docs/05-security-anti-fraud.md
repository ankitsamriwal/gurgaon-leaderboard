# 05 — Security & Anti-Fraud

## Authentication

- OTP-based (phone via SMS provider, or email magic link) — no passwords
  to leak/reuse in v1.
- JWT access tokens, short-lived (15–30 min), refresh token rotation with
  reuse detection (if a used-and-rotated refresh token is presented
  again, revoke the whole session chain — signals token theft).
- Admin accounts: same OTP flow plus IP allowlist or additional TOTP
  factor, given they can approve/reject listings and issue refunds.

## RERA verification

- v1: manual admin verification against the public Haryana RERA search
  portal, with a checklist (project name match, developer name match,
  registration still active/not lapsed) logged in `admin_actions`.
- Fast-follow: scheduled job that re-checks previously verified RERA
  numbers periodically (registrations can lapse or be revoked) and
  flags projects for re-review.
- Never mark `rera_verified=true` automatically from the submission form
  alone — the whole point is that the number is unverified until a human
  or an authoritative API confirms it.

## Rate limiting (Redis-backed, per doc 02 endpoints)

| Endpoint | Limit |
|---|---|
| `POST /auth/otp/request` | 5/hour per phone, 10/hour per IP |
| `POST /projects` | 3/day per user |
| `POST /payments/intent` | 20/hour per user, 50/hour per IP |
| `POST /webhooks/razorpay` | not user-rate-limited, but alert on abnormal volume from a single IP range outside Razorpay's published webhook IP list |

## Anti-fraud / wash-trading detection

- Flag (don't auto-block) patterns for admin review:
  - Same payment method fingerprint or same user funding both the
    "challenger" and a rapid subsequent counter-bid on the same project
    repeatedly.
  - Many small bids from newly-created accounts in a tight time window
    on one project (potential coordinated inflation).
  - A project's bid velocity spiking far outside its historical pattern
    right before a marketing push (could be legitimate hype — flag for
    visibility, not automatic action).
- Log enough (user_id, IP, payment method last-4 if available from
  Razorpay, timestamps) to investigate after the fact without storing
  full card data (Razorpay is PCI-scope, not you — never touch raw card
  numbers).

## Abuse of the submission form

- CAPTCHA (hCaptcha/Turnstile) on `/submit` and `/auth/otp/request`.
- Duplicate `rera_number` rejected at the DB constraint level (doc 01) in
  addition to app-level validation.
- Admin moderation queue is mandatory — no project reaches the public
  leaderboard without a human approval, closing the impersonation/
  defamation risk flagged in doc 06.

## Infrastructure hardening

- All endpoints over TLS only; HSTS enabled.
- Webhook endpoint: verify Razorpay's signature (doc 03) — this is the
  primary defense, but also consider restricting to Razorpay's published
  webhook source IPs as defense-in-depth if your host supports it.
- Secrets in a managed secrets store (not repo, not plain `.env` in
  production containers).
- Dependency scanning (Dependabot/Snyk) and a basic WAF/rate limiter at
  the edge (Cloudflare or equivalent) in front of the API.
- Structured audit logging for every admin action (already modeled as
  `admin_actions` table) and every webhook event (`webhook_events`
  table) — both are your incident-investigation trail.

## Load testing target

Simulate concurrent "beat the leader by ₹1" attempts against the same
project (the designed hot path) — verify the `SELECT ... FOR UPDATE`
transaction serializes correctly under load and no double-counted or
lost bid occurs. This is the single most important test in the whole
system; treat it as a release gate, not a nice-to-have.
