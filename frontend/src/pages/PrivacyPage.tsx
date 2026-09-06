export function PrivacyPage() {
  return (
    <div>
      <h1>Privacy notice</h1>
      <p>
        This page describes, in plain language, what this demo collects and stores. Gurgaon
        Leaderboard is a demonstration project running in mock-payment mode.
      </p>

      <h2>What we collect</h2>
      <ul>
        <li>Phone number or email address, used to sign you in via a one-time code.</li>
        <li>A display name.</li>
        <li>Project submissions you make (name, developer, locality, RERA number).</li>
        <li>
          Bids you place: amount, project, and timestamp. This demo never collects payment details -
          card numbers and UPI IDs would be handled entirely by the payment provider, never by us.
        </li>
      </ul>

      <h2>Why</h2>
      <p>
        To operate the leaderboard: identify who submitted or bid on what, prevent abuse (rate
        limits, duplicate-submission checks), and settle bids correctly.
      </p>

      <h2>Retention</h2>
      <p>
        Bid records are retained even if you delete your account, so the public ranking totals stay
        correct. Your account's personal details (name, phone, email) are removed on request; the
        bid amounts and timestamps remain, disconnected from your identity.
      </p>

      <h2>Requesting export or deletion</h2>
      <p>
        Log in and use the "Request my data" / "Delete my account" actions on your{" "}
        <a href="/dashboard">dashboard</a>. Requests are reviewed and fulfilled by an admin.
      </p>
    </div>
  );
}
