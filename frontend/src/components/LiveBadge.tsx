/** Pulsing indicator for a rank/total change that just arrived over the
 * WS push — never on a plain poll (docs/04). Respects
 * prefers-reduced-motion via the CSS animation being disabled globally
 * for that media query (see src/index.css). */
export function LiveBadge() {
  return (
    <span className="live-badge" aria-label="updated just now" title="Updated just now">
      ●
    </span>
  );
}
