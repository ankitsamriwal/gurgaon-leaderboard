import { useAuthStore } from "../store/auth";

/** docs/04 lists "/dashboard — User's submitted projects + bid history" but
 * docs/02-api-spec.md has no "my submissions" or "my bids" endpoint to back
 * it — a real gap in the spec, not something to paper over with a fake
 * list. This shows what the backend actually exposes about the session
 * today; wire up the list once such an endpoint exists. */
export function DashboardPage() {
  const user = useAuthStore((s) => s.user);

  if (!user) {
    return (
      <p>
        <a href="/login">Log in</a> to view your dashboard.
      </p>
    );
  }

  return (
    <div>
      <h1>Dashboard</h1>
      <p>Signed in as {user.display_name}.</p>
      <p className="dev-hint">
        Your submitted projects and bid history aren't listed here yet — docs/02-api-spec.md doesn't define
        a "my submissions" or "my bids" endpoint. Adding one is a small, self-contained follow-up (filter
        `projects`/`bids` by the current user), not a UI limitation.
      </p>
    </div>
  );
}
