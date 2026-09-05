# 06 — Legal & Compliance Notes

**This document is engineering-facing guidance on what to build to support
legal review — it is not legal advice. Get an actual India-qualified
lawyer to review the product mechanic and ToS before public launch,
particularly given the platform pairs real RERA registration numbers and
real developer/brand names with a paid, gamified ranking.**

## Why this needs review, specifically

- The "pay to outrank a named real company" mechanic risks being read as
  unauthorized commercial use of a developer's name/brand, especially
  when a real government registration number (RERA) is displayed
  alongside a "leader" badge implying some form of endorsement or
  official standing.
- If a third party (not the developer) submits and funds a project's
  ranking, and the public reasonably infers developer endorsement, that
  raises trademark/passing-off and potentially defamation exposure if
  the ranking implies something false or damaging.

## Product/engineering mitigations to build (feed into docs 04/05)

1. **Clear, persistent disclaimer** on every page and every project card:
   independent promotional ranking, not affiliated with or endorsed by
   RERA/Haryana RERA or the named developers, unless explicitly marked
   as a verified developer listing.
2. **"Verified developer listing" vs. "third-party submission" labeling**
   — never let the UI blur this distinction. This is the single highest
   -value legal mitigation and should not be cut from v1 scope.
3. **Admin moderation gate** before any project is public (already in
   doc 05) — gives a human checkpoint to catch obviously
   defamatory/misleading submissions before they're live.
4. **Takedown/dispute process**: a real developer who did not submit
   their own listing needs a fast path to request removal or claim
   ownership. Build a `POST /projects/{id}/dispute` endpoint that routes
   to the admin queue with priority flagging.
5. **RERA number handling**: only display it alongside a verification
   status (doc 05) — never present an unverified number as fact.

## Data protection (India's DPDP Act, 2023)

- Collect only what's needed: phone/email, display name, payment
  metadata (via Razorpay, not raw card data).
- Publish a plain-language privacy notice covering what's collected, why,
  retention period, and how to request deletion.
- Build a data export/delete flow for user accounts (even a manual
  admin-actioned process is acceptable for v1, but the capability must
  exist).
- Retain payment records per Razorpay/RBI-driven retention requirements
  even if a user requests account deletion (financial record-keeping
  obligations typically override a deletion request for transaction
  data specifically — confirm exact retention period with counsel).

## Terms of Service — sections to draft with counsel, informed by this build

- Nature of the ranking (promotional/gamified, not an official
  government or RERA product).
- No guarantee of the accuracy of self-submitted project details beyond
  what's explicitly marked "verified."
- Refund policy for bids (generally: payments for ranking position are
  typically non-refundable once settled, except for fraud/chargeback
  handling per doc 03 — confirm this framing with counsel, as "pay to
  win a ranking" framed as a service fee vs. a wagering-adjacent
  mechanic has different regulatory treatment in India).
- Prohibited conduct: wash trading, impersonation, fraudulent RERA
  numbers — grounds for suspension per the `status='suspended'` project
  state already in the schema.

## Flag for counsel specifically

Whether the "outbid to take #1" mechanic could be characterized as
resembling a game of chance/wagering under Indian law given money is
being competitively staked for a ranking outcome, versus a straightforward
paid-promotion/advertising service. This characterization materially
affects which regulations apply and should be resolved **before** public
launch, not treated as a post-launch cleanup item.
