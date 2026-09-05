# 03 — Payment Integration (Razorpay)

## Core rule

**Client-side checkout success is never trusted for ranking.** The
frontend's `handler` callback from Razorpay Checkout may only show an
optimistic "processing your bid…" state. The `bids` table is written
exclusively by the webhook handler after independent signature
verification.

## Flow

1. Client calls `POST /payments/intent` (doc 02) → server creates a
   Razorpay Order, stores `payment_intents` row (`status=order_created`).
2. Client opens Razorpay Checkout with `order_id`.
3. On checkout success, client's callback hits
   `POST /payments/confirm-attempt` (optional, UX-only): sets intent
   status to `pending_webhook` and shows a "confirming…" spinner. **This
   endpoint must not write to `bids` or update project totals.**
4. Razorpay sends `payment.captured` (and/or `order.paid`) webhook to
   `POST /webhooks/razorpay`.
5. Webhook handler:
   a. Reads raw body + `X-Razorpay-Signature` header.
   b. Verifies HMAC-SHA256 signature using the webhook secret
      (**different secret from the API key**, configured in the Razorpay
      dashboard).
   c. Rejects (400, no processing) if invalid — log to `webhook_events`
      with `signature_valid=false` regardless, for audit.
   d. Checks `razorpay_event_id` against `webhook_events` — if already
      `processed=true`, return 200 immediately (idempotent replay, no
      double-processing). Razorpay retries webhooks; this is expected.
   e. Looks up the matching `payment_intents` row by
      `razorpay_order_id`.
   f. Verifies `payment.amount` matches `payment_intents.amount_paise`
      exactly. Mismatch → flag to `admin_actions`, do not insert a bid,
      alert.
   g. Runs the transaction from doc 01 (insert `bids` row, update
      `projects.cached_total_paise`, update `leadership_log`).
   h. Marks `webhook_events.processed = true`.
6. WebSocket push to connected clients with new leaderboard state.

## Idempotency

- `payment_intents.idempotency_key` is unique — client generates a fresh
  UUID per "Pay" button click; if the client retries the same click
  (double-tap, network retry), the server returns the existing intent
  instead of creating a second order.
- `webhook_events.razorpay_event_id` is unique — protects against
  Razorpay's documented at-least-once webhook delivery.
- `bids.razorpay_payment_id` is unique — a second attempt to insert a bid
  for the same `payment_id` fails at the DB constraint level as a last
  line of defense even if application logic has a bug.

## Signature verification (reference)

```python
import hmac, hashlib

def verify_webhook_signature(raw_body: bytes, signature: str, webhook_secret: str) -> bool:
    expected = hmac.new(
        webhook_secret.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
```
Always verify against the **raw request body bytes**, before any JSON
parsing — re-serializing and re-hashing a parsed object will produce a
different signature and cause false rejections or, worse, false
acceptances if implemented sloppily.

## Reconciliation job (nightly, e.g. 2 AM IST)

1. Pull the previous day's settled payments from Razorpay's
   `payments` API (or settlement report export).
2. For each Razorpay payment, confirm a matching `bids` row exists with
   the same `razorpay_payment_id` and `amount_paise`.
3. For each `bids` row created yesterday, confirm the corresponding
   Razorpay payment is `captured` (not `failed`/`refunded` without a
   matching `reversed=true` flag).
4. Recompute every project's total from the ledger
   (`SUM(amount_paise) WHERE reversed=false`) and diff against
   `cached_total_paise`. Any mismatch = alert (Slack/email/PagerDuty),
   auto-correct the cache only after the alert fires, never silently.
5. Store the report; expose via `GET /admin/reconciliation/report`.

## Refunds & chargebacks

- Razorpay sends `refund.processed` / `payment.dispute.created` webhooks
  — handle both.
- On refund: mark the corresponding `bids.reversed = true`,
  `reversed_at`, `reversal_reason`, then run the same total-recalculation
  transaction as a normal bid (subtracting instead of adding).
- **Decide and document product behavior**: does a refunded bid
  retroactively change historical "leader for X days" attribution? Ship
  v1 answer: no retroactive rewrite of `leadership_log` — only current
  totals and future leadership are affected. State this explicitly in
  the public ToS/FAQ.

## Mock payment mode

- Exists only for demos/dev. Implement as a separate code path compiled
  out via a build-time constant (e.g. `if settings.ENVIRONMENT ==
  "production": raise HTTPException(404)` at the route level, and ideally
  the route itself is not even registered when building the production
  container image — check at app-factory/startup time, not per-request).
- Mock bids are flagged `is_mock=true` and excluded from all public
  leaderboard queries by default (`WHERE is_mock = FALSE`).

## Secrets handling

- Razorpay Key ID: safe to expose to frontend (needed for Checkout).
- Razorpay Key Secret + Webhook Secret: server-side only, in a secrets
  manager (not `.env` committed anywhere, not in frontend build).
- Rotate webhook secret if ever suspected leaked; Razorpay supports
  multiple active webhook secrets during rotation.
