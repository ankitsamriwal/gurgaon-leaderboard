import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { apiFetch, ApiRequestError, formatPaise } from "../lib/api";
import { useAuthStore } from "../store/auth";

interface MyBid {
  bid_id: string;
  project_id: string;
  project_name: string;
  amount_paise: number;
  reversed: boolean;
  created_at: string;
}

interface MyProject {
  project_id: string;
  name: string;
  developer_name: string;
  locality: string;
  status: string;
  total_paise: number;
  bid_count: number;
}

interface AccountMe {
  bids: MyBid[];
  projects: MyProject[];
}

export function DashboardPage() {
  const user = useAuthStore((s) => s.user);
  const [requestStatus, setRequestStatus] = useState<string | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);

  const me = useQuery({
    queryKey: ["account", "me"],
    queryFn: () => apiFetch<AccountMe>("/account/me"),
    enabled: !!user,
  });

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
          ? "Export requested - an admin will follow up with your data."
          : "Deletion requested - an admin will review and anonymize your account.",
      );
    } catch (err) {
      setRequestError(err instanceof ApiRequestError ? err.message : "Could not file that request.");
    }
  }

  const statusLabel: Record<string, string> = {
    pending_review: "Under review",
    live: "Live",
    rejected: "Rejected",
    suspended: "Suspended",
  };

  return (
    <div>
      <h1>Dashboard</h1>
      <p>Signed in as {user.display_name}.</p>

      <h2>Your bids</h2>
      {me.isLoading && <p>Loading…</p>}
      {me.isError && <p role="alert">Could not load your bids right now.</p>}
      {me.data && me.data.bids.length === 0 && (
        <p>No bids yet. Pick a project on the <Link to="/">leaderboard</Link> and take #1.</p>
      )}
      {me.data && me.data.bids.length > 0 && (
        <ul>
          {me.data.bids.map((bid) => (
            <li key={bid.bid_id}>
              <Link to={`/projects/${bid.project_id}`}>{bid.project_name}</Link>
              {" - "}
              {formatPaise(bid.amount_paise)}
              {bid.reversed ? " (refunded)" : ""}
              {" - "}
              {new Date(bid.created_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}
            </li>
          ))}
        </ul>
      )}

      <h2>Your submitted projects</h2>
      {me.data && me.data.projects.length === 0 && (
        <p>
          Nothing submitted yet. <Link to="/submit">Submit a project</Link> - listings go live after
          RERA verification.
        </p>
      )}
      {me.data && me.data.projects.length > 0 && (
        <ul>
          {me.data.projects.map((project) => (
            <li key={project.project_id}>
              <Link to={`/projects/${project.project_id}`}>{project.name}</Link>
              {" - "}
              {project.developer_name}, {project.locality}
              {" - "}
              {statusLabel[project.status] ?? project.status}
              {" - "}
              {formatPaise(project.total_paise)} across {project.bid_count}{" "}
              {project.bid_count === 1 ? "bid" : "bids"}
            </li>
          ))}
        </ul>
      )}

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
