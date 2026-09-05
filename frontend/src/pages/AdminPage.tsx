import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, ApiRequestError } from "../lib/api";
import { useAuthStore } from "../store/auth";
import { ReconciliationPanel } from "../components/ReconciliationPanel";

interface PendingProject {
  id: string;
  name: string;
  developer_name: string;
  locality: string;
  rera_number: string;
  rera_verified: boolean;
  rera_lookup_url: string;
}

interface PendingClaim {
  id: string;
  project_id: string;
  claimant_user_id: string;
  document_url: string | null;
}

interface PendingDispute {
  id: string;
  project_id: string;
  filed_by_user_id: string;
  reason: string;
  contact_email: string | null;
  priority: boolean;
}

interface PendingDataRequest {
  id: string;
  user_id: string;
  request_type: string;
}

export function AdminPage() {
  const user = useAuthStore((s) => s.user);
  const queryClient = useQueryClient();
  const [forbidden, setForbidden] = useState(false);
  const [reverseBidId, setReverseBidId] = useState("");

  const pendingProjects = useQuery({
    queryKey: ["admin", "projects", "pending"],
    queryFn: async () => {
      try {
        const resp = await apiFetch<{ projects: PendingProject[] }>("/admin/projects/pending");
        return resp.projects;
      } catch (err) {
        if (err instanceof ApiRequestError && err.code === "FORBIDDEN") setForbidden(true);
        throw err;
      }
    },
    enabled: !!user,
    retry: false,
  });

  const pendingClaims = useQuery({
    queryKey: ["admin", "claims", "pending"],
    queryFn: async () => {
      const resp = await apiFetch<{ claims: PendingClaim[] }>("/admin/claims/pending");
      return resp.claims;
    },
    enabled: !!user && !forbidden,
    retry: false,
  });

  const pendingDisputes = useQuery({
    queryKey: ["admin", "disputes", "pending"],
    queryFn: async () => {
      const resp = await apiFetch<{ disputes: PendingDispute[] }>("/admin/disputes/pending");
      return resp.disputes;
    },
    enabled: !!user && !forbidden,
    retry: false,
  });

  const pendingDataRequests = useQuery({
    queryKey: ["admin", "data-requests", "pending"],
    queryFn: async () => {
      const resp = await apiFetch<{ requests: PendingDataRequest[] }>("/admin/data-requests/pending");
      return resp.requests;
    },
    enabled: !!user && !forbidden,
    retry: false,
  });

  const approveProject = useMutation({
    mutationFn: (id: string) => apiFetch(`/admin/projects/${id}/approve`, { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "projects", "pending"] }),
  });

  const rejectProject = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      apiFetch(`/admin/projects/${id}/reject`, { method: "POST", body: JSON.stringify({ reason }) }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "projects", "pending"] }),
  });

  const verifyRera = useMutation({
    mutationFn: (id: string) => apiFetch(`/admin/projects/${id}/verify-rera`, { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "projects", "pending"] }),
  });

  const approveClaim = useMutation({
    mutationFn: (id: string) => apiFetch(`/admin/claims/${id}/approve`, { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "claims", "pending"] }),
  });

  const rejectClaim = useMutation({
    mutationFn: (id: string) => apiFetch(`/admin/claims/${id}/reject`, { method: "POST", body: JSON.stringify({}) }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "claims", "pending"] }),
  });

  const reverseBid = useMutation({
    mutationFn: (id: string) => apiFetch(`/admin/bids/${id}/reverse`, { method: "POST" }),
    onSuccess: () => {
      setReverseBidId("");
      queryClient.invalidateQueries({ queryKey: ["leaderboard"] });
    },
  });

  const resolveDispute = useMutation({
    mutationFn: ({ id, suspend }: { id: string; suspend: boolean }) =>
      apiFetch(`/admin/disputes/${id}/resolve`, {
        method: "POST",
        body: JSON.stringify({ suspend_project: suspend }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "disputes", "pending"] });
      queryClient.invalidateQueries({ queryKey: ["leaderboard"] });
    },
  });

  const fulfillDataRequest = useMutation({
    mutationFn: (id: string) => apiFetch(`/admin/data-requests/${id}/fulfill`, { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "data-requests", "pending"] }),
  });

  if (!user) {
    return (
      <p>
        <a href="/login">Log in</a> as an admin to continue.
      </p>
    );
  }

  if (forbidden) return <p role="alert">You don't have admin access.</p>;

  return (
    <div>
      <h1>Admin</h1>

      <h2>Pending projects</h2>
      <ul>
        {pendingProjects.data?.map((p) => (
          <li key={p.id}>
            <strong>{p.name}</strong> ({p.developer_name}, {p.locality}) — RERA {p.rera_number}{" "}
            {p.rera_verified ? "✅" : "⏳"}
            <div>
              <a href={p.rera_lookup_url} target="_blank" rel="noreferrer">
                Look up on Haryana RERA portal
              </a>
            </div>
            <button onClick={() => verifyRera.mutate(p.id)}>Mark RERA verified</button>
            <button onClick={() => approveProject.mutate(p.id)}>Approve</button>
            <button
              onClick={() => {
                const reason = window.prompt("Reason for rejection?") ?? "";
                rejectProject.mutate({ id: p.id, reason });
              }}
            >
              Reject
            </button>
          </li>
        ))}
        {pendingProjects.data?.length === 0 && <li>Nothing pending.</li>}
      </ul>

      <h2>Pending developer claims</h2>
      <ul>
        {pendingClaims.data?.map((c) => (
          <li key={c.id}>
            Project {c.project_id} — claimed by user {c.claimant_user_id}
            {c.document_url && (
              <>
                {" "}
                (<a href={c.document_url} target="_blank" rel="noreferrer">document</a>)
              </>
            )}
            <button onClick={() => approveClaim.mutate(c.id)}>Approve</button>
            <button onClick={() => rejectClaim.mutate(c.id)}>Reject</button>
          </li>
        ))}
        {pendingClaims.data?.length === 0 && <li>Nothing pending.</li>}
      </ul>

      <h2>Refund / chargeback a bid</h2>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (reverseBidId) reverseBid.mutate(reverseBidId);
        }}
      >
        <label htmlFor="reverse-bid-id">Bid ID</label>
        <input
          id="reverse-bid-id"
          value={reverseBidId}
          onChange={(e) => setReverseBidId(e.target.value)}
          placeholder="bid uuid"
        />
        <button type="submit" disabled={reverseBid.isPending}>
          {reverseBid.isPending ? "Reversing…" : "Reverse bid"}
        </button>
        {reverseBid.isError && (
          <p role="alert">
            {reverseBid.error instanceof ApiRequestError ? reverseBid.error.message : "Could not reverse that bid."}
          </p>
        )}
      </form>

      <h2>Pending disputes</h2>
      <ul>
        {pendingDisputes.data?.map((d) => (
          <li key={d.id}>
            {d.priority && <strong>[priority] </strong>}
            Project {d.project_id} — "{d.reason}"{d.contact_email && ` (${d.contact_email})`}
            <button onClick={() => resolveDispute.mutate({ id: d.id, suspend: false })}>
              Resolve (no action)
            </button>
            <button onClick={() => resolveDispute.mutate({ id: d.id, suspend: true })}>
              Resolve & suspend project
            </button>
          </li>
        ))}
        {pendingDisputes.data?.length === 0 && <li>Nothing pending.</li>}
      </ul>

      <h2>Pending data requests</h2>
      <ul>
        {pendingDataRequests.data?.map((r) => (
          <li key={r.id}>
            {r.request_type} — user {r.user_id}
            <button onClick={() => fulfillDataRequest.mutate(r.id)}>Mark fulfilled</button>
          </li>
        ))}
        {pendingDataRequests.data?.length === 0 && <li>Nothing pending.</li>}
      </ul>

      <ReconciliationPanel />
    </div>
  );
}
