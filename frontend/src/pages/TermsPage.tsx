export function TermsPage() {
  return (
    <div>
      <h1>Terms of Service</h1>
      <p>
        Gurgaon Leaderboard is a demonstration project. It runs in mock-payment mode: no real money
        is charged, no real payment method is collected, and bids have no monetary value.
      </p>

      <h2>What this is</h2>
      <ul>
        <li>
          A public, pay-to-rank promotional leaderboard for Gurgaon real estate projects. A project's
          rank reflects only the cumulative bids placed on it - nothing else.
        </li>
        <li>
          This is not an official government, RERA, or Haryana RERA product, and it is not affiliated
          with or endorsed by the listed developers unless a listing is explicitly marked as a verified
          developer listing.
        </li>
        <li>
          Rankings are not investment advice, not a measure of project quality, and not a
          recommendation to buy property.
        </li>
      </ul>

      <h2>Listing accuracy</h2>
      <p>
        Project details are self-submitted. We check RERA registration numbers against the public
        Haryana RERA portal before a listing goes live, but beyond listings marked "verified" we do
        not guarantee the accuracy of any project detail. Always verify on the official Haryana RERA
        portal before making any decision.
      </p>

      <h2>Bids and refunds</h2>
      <p>
        While the board runs in mock-payment mode, every payment is simulated and no refund is
        needed because no money moves. If real payments are ever switched on, bids are payments for
        promotional placement and are non-refundable once settled, except where a listing is removed
        for fraud.
      </p>

      <h2>Prohibited conduct</h2>
      <ul>
        <li>Wash trading or bidding on your own listing to fake demand.</li>
        <li>Impersonating a developer, broker, or another person.</li>
        <li>Submitting fraudulent or invalid RERA numbers.</li>
        <li>Abusing the service, its APIs, or other users.</li>
      </ul>
      <p>We may suspend listings, reverse bids, and block accounts that break these rules.</p>
    </div>
  );
}
