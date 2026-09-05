/** docs/06-legal-compliance.md is explicit that ToS sections need to be
 * "drafted with counsel" — this is deliberately a placeholder naming what
 * needs to be there, not a drafted ToS. Do not treat this as legal text.
 */
export function TermsPage() {
  return (
    <div>
      <h1>Terms of Service</h1>
      <p role="alert">
        This page is a placeholder. Real Terms of Service must be drafted by an India-qualified lawyer
        before public launch — see docs/06-legal-compliance.md. Sections that need drafting:
      </p>
      <ul>
        <li>Nature of the ranking (promotional/gamified, not an official government or RERA product).</li>
        <li>No guarantee of the accuracy of self-submitted project details beyond what's explicitly
          marked "verified."</li>
        <li>Refund policy for bids.</li>
        <li>Prohibited conduct: wash trading, impersonation, fraudulent RERA numbers.</li>
      </ul>
      <p className="dev-hint">
        Flagged for counsel specifically, before launch (docs/06): whether the "outbid to take #1"
        mechanic could be characterized as resembling a game of chance/wagering under Indian law, versus
        a straightforward paid-promotion/advertising service. This materially affects which regulations
        apply and is not resolved by anything in this codebase.
      </p>
    </div>
  );
}
