import { useState } from "react";
import { apiFetch, ApiRequestError } from "../lib/api";
import { useAuthStore } from "../store/auth";

/** docs/04 lists "/dashboard — User's submitted projects + bid history" but
 * docs/02-api-spec.md has no "my submissions" or "my bids" endpoint to back
 * it — a real gap in the spec, not something to paper over with a fake
 * list. This shows what the backend actually exposes about the session
 * today; wire up the list once such an endpoint exists. */
export function DashboardPage() {
  const user = useAuthStore((s) => s.user);
  const [requestStatus, setRequestStatus] = useState<string | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);

  if (!user) {
    return (
      <p>
        <a href="/login">Log in</a> to view your dashboard.
      </p>
    );
  }

  async function requestData(type: "export" | "delete") {
    setRequestError(null);
    setRequestStatus(null);
    try {
      await apiFetch("/account/data-request", { method: "POST", body: JSON.stringify({ request_type: type }) });
      setRequestStatus(
        type === "export"
          ? "Export requested — an admin will follow up with your data."
          : "Deletion requested — an admin will review and anonymize your account.",
      );
    } catch (err) {
      setRequestError(err instanceof ApiRequestError ? err.message : "Could not file that request.");
    }
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

      <h2>Your data</h2>
      <p>
        Per our <a href="/privacy">privacy notice</a>, you can request a copy of your data or ask us to
        delete your account.
      </p>
      <button onClick={() => requestData("export")}>Request my data</button>{" "}
      <button onClick={() => requestData("delete")}>Delete my account</button>
      {requestStatus && <p role="status">{requestStatus}</p>}
      {requestError && <p role="alert">{requestError}</p>}
    </div>
  );
}
