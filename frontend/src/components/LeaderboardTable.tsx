import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { formatPaise } from "../lib/api";
import type { LeaderboardEntry, LeaderboardResponse } from "../types";
import { useAuthStore } from "../store/auth";
import { BidModal } from "./BidModal";
import { LiveBadge } from "./LiveBadge";

// Bidding starts from Rs 500 - the absolute floor for any bid.
const MIN_BID_PAISE = 50_000;

function RankLogo({ row }: { row: LeaderboardEntry }) {
  const [broken, setBroken] = useState(false);
  if (row.logo_url && !broken) {
    return (
      <img
        className="rank-logo"
        src={row.logo_url}
        alt=""
        loading="lazy"
        onError={() => setBroken(true)}
      />
    );
  }
  return <span className="rank-logo rank-logo-fallback" aria-hidden="true">{row.name.charAt(0).toUpperCase()}</span>;
}

export function LeaderboardTable({
  data,
  justChanged,
}: {
  data: LeaderboardResponse;
  justChanged: Set<string>;
}) {
  const user = useAuthStore((s) => s.user);
  const navigate = useNavigate();
  const [bidTarget, setBidTarget] = useState<string | null>(null);

  const leaderTotal = data.rankings[0]?.total_paise ?? 0;
  const leaderId = data.leader?.project_id ?? null;
  const dailyId = data.daily_topper?.project_id ?? null;

  const selected = data.rankings.find((r) => r.project_id === bidTarget) ?? null;
  const selectedIsLeader = selected?.project_id === leaderId;
  const minToTakeLead =
    selected && !selectedIsLeader
      ? Math.max(leaderTotal - selected.total_paise + 100, MIN_BID_PAISE)
      : null;

  function openBid(projectId: string) {
    if (!user) {
      navigate("/login");
      return;
    }
    setBidTarget(projectId);
  }

  return (
    <div className="board">
      {data.rankings.map((row) => {
        const isLeader = row.project_id === leaderId;
        const toLead = leaderTotal - row.total_paise + 100;
        return (
          <div
            key={row.project_id}
            className={[
              "rank-row",
              isLeader ? "is-leader" : "",
              justChanged.has(row.project_id) ? "row-live" : "",
            ].join(" ")}
          >
            <span className="rank-no">{row.rank}</span>
            <RankLogo row={row} />
            <div className="rank-main">
              <h2 className="rank-name">
                <Link to={`/projects/${row.project_id}`} style={{ textDecoration: "none", color: "inherit" }}>
                  {row.name}
                </Link>
                <span className="badges">
                  {row.is_sample && <span className="badge badge-sample">Sample</span>}
                  {isLeader && <span className="badge badge-leader">On top</span>}
                  {row.project_id === dailyId && !isLeader && (
                    <span className="badge badge-daily">Today's mover</span>
                  )}
                  {justChanged.has(row.project_id) && <LiveBadge />}
                </span>
              </h2>
              <div className="rank-sub">
                {row.developer_name} · {row.locality}
              </div>
              {(row.property_type || row.unit_sizes || row.amenities) && (
                <div className="rank-meta">
                  {[row.property_type, row.unit_sizes].filter(Boolean).join(" · ")}
                  {row.amenities && <span className="rank-amenities">{row.amenities}</span>}
                </div>
              )}
            </div>
            <div className="rank-amount">
              <span className="amount">{formatPaise(row.total_paise)}</span>
              <span className="bid-count">{row.bid_count} {row.bid_count === 1 ? "bid" : "bids"}</span>
            </div>
            <button
              className={isLeader ? "take1 outline" : "take1"}
              onClick={() => openBid(row.project_id)}
            >
              {isLeader ? "Extend the lead" : `Take #1 for ${formatPaise(toLead)}`}
            </button>
          </div>
        );
      })}
      {data.rankings.length === 0 && (
        <p className="empty-state">No live projects yet - bidding starts from ₹500.</p>
      )}

      {selected && (
        <BidModal
          projectId={selected.project_id}
          projectName={selected.name}
          currentTotalPaise={selected.total_paise}
          minToTakeLeadPaise={minToTakeLead}
          onClose={() => setBidTarget(null)}
        />
      )}
    </div>
  );
}
