/** docs/06-legal-compliance.md's Data protection section: "Publish a
 * plain-language privacy notice covering what's collected, why, retention
 * period, and how to request deletion." This describes what the system
 * actually collects and stores — it is NOT legal advice and is NOT a
 * substitute for a real privacy policy reviewed by counsel, exactly as
 * docs/06 itself opens by saying about the whole document. Do not treat
 * this page as launch-ready without that review.
 */
export function PrivacyPage() {
  return (
    <div>
      <h1>Privacy notice</h1>
      <p className="dev-hint">
        This page describes what this system collects and stores, in plain language. It is not a
        substitute for a legal privacy policy — get an India-qualified lawyer to review it against the
        Digital Personal Data Protection Act, 2023 before public launch (see docs/06-legal-compliance.md).
      </p>

      <h2>What we collect</h2>
      <ul>
        <li>Phone number or email address, used to sign you in via a one-time code.</li>
        <li>A display name.</li>
        <li>Project submissions you make (name, developer, locality, RERA number).</li>
        <li>Bids you place: amount, project, and timestamp. Payment details themselves (card
          numbers, UPI IDs) are handled entirely by Razorpay — we never see or store them.</li>
      </ul>

      <h2>Why</h2>
      <p>
        To operate the leaderboard: identify who submitted or bid on what, prevent abuse (rate limits,
        duplicate-submission checks), and settle payments correctly.
      </p>

      <h2>Retention</h2>
      <p>
        Bid and payment records are retained even if you delete your account — financial
        record-keeping obligations require this for transaction data specifically. Your account's
        personal details (name, phone, email) are removed on request; the underlying bid amounts and
        timestamps remain, disconnected from your identity.
      </p>

      <h2>Requesting export or deletion</h2>
      <p>
        Log in and use the "Request my data" / "Delete my account" actions on your{" "}
        <a href="/dashboard">dashboard</a>. Requests are reviewed and fulfilled by an admin — this is a
        manual process for now, but the capability exists per docs/06.
      </p>
    </div>
  );
}
