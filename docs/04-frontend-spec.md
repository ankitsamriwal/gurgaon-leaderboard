# 04 — Frontend Spec

Stack: React + TypeScript + Vite. State: React Query (server state) +
lightweight local state (Zustand or context) for auth/session — avoid
Redux boilerplate for an app this size.

## Pages / routes

| Route | Purpose | Auth |
|---|---|---|
| `/` | Public leaderboard (top 5, daily topper, leader timer) | none |
| `/projects/:id` | Project detail, full bid history, "Place a bid" CTA | none to view, auth to bid |
| `/submit` | Submit a new project form | required |
| `/login` | Phone/email OTP flow | none |
| `/dashboard` | User's submitted projects + bid history | required |
| `/admin` | Moderation queue, RERA verification, refunds | admin role |

## Components

- `LeaderboardTable` — top 5, live-updating via WebSocket subscription;
  shows rank, name, developer, locality, total (formatted ₹), bid count,
  "leader for Xd Yh" timer computed client-side from `leader_since`.
- `LiveBadge` — pulsing indicator when a rank change just happened
  (animate on WS diff, not on poll).
- `BidModal` — shows current total, minimum amount needed to take #1 (if
  applicable), amount input, Razorpay Checkout trigger.
  - Must call `POST /payments/intent` first, then open Razorpay Checkout
    with the returned `order_id` — never open Checkout with a
    client-computed amount alone.
  - On Checkout success callback: show "confirming your bid…" state,
    poll `GET /projects/:id` (or wait on WS) for the bid to actually
    appear — **do not optimistically render the new rank before the
    webhook has landed.** This is the one place where resisting the
    urge to feel "instant" matters more than UX polish; showing a bid
    that later fails webhook verification (rare, but possible) is worse
    than a 2–5 second confirmation delay.
- `ProjectSubmitForm` — RERA number field with inline format validation
  and a note that it will be manually verified before the listing goes
  live; opening bid amount; developer/locality fields.
- `AdminModerationQueue` — pending projects list, approve/reject with
  reason, RERA verification checkbox with a link out to the Haryana RERA
  public search.
- `ReconciliationPanel` (admin) — surfaces the nightly job's mismatch
  report, if any.

## Real-time handling

- Establish one WebSocket connection at app root (`/ws/leaderboard`),
  fan out updates via context to any subscribed component.
- Reconnect with exponential backoff; fall back to 5–10s polling of
  `GET /projects/leaderboard` if WS fails repeatedly (don't leave users
  on a silently stale leaderboard).

## Trust & transparency UI details (do these — they double as anti-fraud/legal cover)

- Every project card shows a "RERA Verified ✅ / Pending verification ⏳"
  badge — never imply verification before `rera_verified=true`.
- Unclaimed listings show "Not verified as an official developer
  listing" — ties back to `claimed_by` in the schema.
- Footer/disclaimer visible on every page: "This is an independent
  promotional ranking, not affiliated with or endorsed by RERA, Haryana
  RERA, or the listed developers unless marked 'Verified developer
  listing.'" (Finalize exact wording with the legal doc, `06`.)

## Error states to design explicitly (map to API error codes from doc 02)

- `AMOUNT_TOO_LOW` — show the exact minimum required, live-updated if
  someone else takes the lead while the modal is open.
- `IDEMPOTENCY_CONFLICT` — silently resolve to the existing intent, no
  user-visible error.
- `RATE_LIMITED` — clear "try again in X minutes" messaging.
- `PROJECT_NOT_LIVE` — shouldn't normally be reachable from the UI, but
  handle gracefully (project was suspended mid-session).

## Accessibility & mobile

- Bid amounts and RERA numbers are numeric/alphanumeric inputs with
  appropriate `inputmode` attributes for mobile keyboards.
- Leaderboard table collapses to stacked cards below ~640px.
- Live-update animations respect `prefers-reduced-motion`.
