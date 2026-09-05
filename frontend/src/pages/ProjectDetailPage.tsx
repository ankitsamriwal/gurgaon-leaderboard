import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, formatPaise, ApiRequestError } from "../lib/api";
import { useAuthStore } from "../store/auth";
import { BidModal } from "../components/BidModal";
import { Disclaimer } from "../components/Disclaimer";
import { useLeaderboard } from "../hooks/useLeaderboard";
import type { ProjectDetail } from "../types";

export function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const user = useAuthStore((s) => s.user);
  const [showBidModal, setShowBidModal] = useState(false);
  const { data: leaderboard } = useLeaderboard();

  const { data, isLoading, error } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => apiFetch<ProjectDetail>(`/projects/${projectId}`),
    enabled: !!projectId,
  });

  if (isLoading) return <p>Loading…</p>;

  if (error) {
    const notLive = error instanceof ApiRequestError && error.code === "PROJECT_NOT_LIVE";
    return <p role="alert">{notLive ? "This project isn't public." : "Could not load this project."}</p>;
  }

  if (!data || !projectId) return null;

  const currentLeaderTotal = leaderboard?.rankings[0]?.total_paise ?? null;
  const isAlreadyLeader = leaderboard?.rankings[0]?.project_id === projectId;
  const minToTakeLead =
    currentLeaderTotal !== null && !isAlreadyLeader ? currentLeaderTotal - data.total_paise + 1 : null;

  return (
    <div>
      <h1>{data.name}</h1>
      <p>
        {data.developer_name} — {data.locality}
      </p>

      <p>
        {data.rera_verified ? (
          <span className="badge badge-verified">RERA Verified ✅</span>
        ) : (
          <span className="badge badge-pending">Pending verification ⏳</span>
        )}{" "}
        {data.is_verified_developer_listing ? (
          <span className="badge badge-verified">Verified developer listing</span>
        ) : (
          <span className="badge badge-pending">Not verified as an official developer listing</span>
        )}
      </p>

      <p>RERA number: {data.rera_number}</p>
      {data.project_url && (
        <p>
          <a href={data.project_url} target="_blank" rel="noreferrer">
            Project website
          </a>
        </p>
      )}

      <h2>{formatPaise(data.total_paise)} raised</h2>
      <p>{data.bid_count} bids</p>

      {user ? (
        <button onClick={() => setShowBidModal(true)}>Place a bid</button>
      ) : (
        <p>
          <a href="/login">Log in</a> to place a bid.
        </p>
      )}

      <h3>Recent bids</h3>
      <ul>
        {data.bids.items.map((bid) => (
          <li key={bid.id}>
            {formatPaise(bid.amount_paise)} — {bid.bidder_label ?? "anonymous"} —{" "}
            {new Date(bid.created_at).toLocaleString()}
          </li>
        ))}
        {data.bids.items.length === 0 && <li>No bids yet.</li>}
      </ul>

      <Disclaimer />

      {showBidModal && (
        <BidModal
          projectId={projectId}
          projectName={data.name}
          currentTotalPaise={data.total_paise}
          minToTakeLeadPaise={minToTakeLead}
          onClose={() => setShowBidModal(false)}
        />
      )}
    </div>
  );
}
