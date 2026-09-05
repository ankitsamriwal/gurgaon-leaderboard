/** docs/04-frontend-spec.md: "Footer/disclaimer visible on every page."
 * Exact wording per docs/04; docs/06-legal-compliance.md says to finalize
 * it with counsel before launch (Phase 8) — this is the placeholder that
 * makes the requirement visible now rather than an afterthought.
 */
export function Disclaimer() {
  return (
    <p className="disclaimer">
      This is an independent promotional ranking, not affiliated with or
      endorsed by RERA, Haryana RERA, or the listed developers unless marked
      "Verified developer listing."
    </p>
  );
}
