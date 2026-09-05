# 02 — API Spec

Base URL: `/api/v1`. All authenticated endpoints require `Authorization:
Bearer <JWT>`. All money fields are integers in paise.

## Auth

### `POST /auth/otp/request`
Request an OTP to phone or email.
```json
{ "phone": "+919999999999" }
```
→ `202 { "request_id": "uuid" }`

### `POST /auth/otp/verify`
```json
{ "request_id": "uuid", "otp": "123456" }
```
→ `200 { "access_token": "jwt", "user": { "id": "...", "display_name": "..." } }`

Rate limit: 5 requests/hour per phone, 10/hour per IP.

## Projects

### `GET /projects/leaderboard`
Public, no auth. Returns top 5 + summary stats. Cached in Redis, 5–10s TTL.
```json
{
  "leader": { "project_id": "...", "leader_since": "2026-09-01T10:00:00Z" },
  "daily_topper": { "project_id": "...", "last_24h_paise": 500000 },
  "rankings": [
    { "rank": 1, "project_id": "...", "name": "...", "developer_name": "...",
      "locality": "...", "total_paise": 1250000, "bid_count": 14 }
  ]
}
```

### `GET /projects/{id}`
Public. Full project detail + bid history (paginated).

### `POST /projects` — *auth required*
Submit a new project. Goes to `pending_review`, not visible on public
leaderboard until admin-approved.
```json
{
  "name": "...", "developer_name": "...", "locality": "...",
  "rera_number": "...", "project_url": "...", "opening_bid_paise": 100000
}
```
→ `201 { "project_id": "...", "status": "pending_review" }`

Validation:
- `rera_number` format-checked against Haryana RERA number pattern.
- Reject duplicate `rera_number` on any non-rejected project.
- Rate limit: 3 submissions/day per user.

### `POST /projects/{id}/claim` — *auth required, developer role*
Start a developer ownership claim (domain email match + document upload).
Goes to an admin queue; does not auto-approve.

## Bidding / Payments

### `POST /payments/intent` — *auth required*
Client calls this first, before showing Razorpay checkout.
```json
{
  "project_id": "...", "amount_paise": 150000,
  "idempotency_key": "client-generated-uuid"
}
```
Server logic:
1. If `idempotency_key` already exists → return the existing intent
   (never create a duplicate).
2. Validate `amount_paise` ≥ (current leader's total − this project's
   current total + 1) **only if** the UI is framed as "beat the leader" —
   otherwise any positive amount is accepted as an incremental bid.
3. Create Razorpay Order via Razorpay Orders API.
4. Insert `payment_intents` row, status `order_created`.

→ `201 { "intent_id": "...", "razorpay_order_id": "...", "amount_paise": 150000, "razorpay_key_id": "..." }`

### `POST /payments/mock` — *auth required, non-prod builds only*
Simulates a successful payment without Razorpay, for demos. **Compiled
out of production builds** (see `03-payment-integration.md`), not just
env-flagged.

### Webhook: `POST /webhooks/razorpay`
No user auth — authenticated via Razorpay signature header instead. See
`03-payment-integration.md` for full verification + processing flow. This
is the **only** endpoint that ever inserts a row into `bids`.

## Admin (separate auth scope: `role = admin`)

### `GET /admin/projects/pending`
List `pending_review` projects with RERA lookup helper links.

### `POST /admin/projects/{id}/approve`
### `POST /admin/projects/{id}/reject`
```json
{ "reason": "..." }
```

### `POST /admin/projects/{id}/verify-rera`
Marks `rera_verified = true` after manual check against the Haryana RERA
public portal.

### `POST /admin/bids/{id}/reverse`
Handles refund/chargeback: sets `reversed = true`, recalculates the
project's `cached_total_paise` inside a transaction, logs to
`admin_actions`.

### `GET /admin/reconciliation/report`
Returns latest nightly reconciliation job output (see doc 03).

## Real-time updates

`WS /ws/leaderboard` — server pushes a diff whenever the top-5 ordering or
any project's total changes (triggered from the same DB transaction that
accepts a webhook-verified bid). Fallback: clients without WS support
poll `GET /projects/leaderboard` every 5–10s.

## Standard error shape

```json
{ "error": { "code": "RERA_DUPLICATE", "message": "..." } }
```

Use specific error codes (`RERA_DUPLICATE`, `AMOUNT_TOO_LOW`,
`IDEMPOTENCY_CONFLICT`, `RATE_LIMITED`, `PROJECT_NOT_LIVE`, etc.) — the
frontend needs to branch on these, not just show a generic failure toast.
