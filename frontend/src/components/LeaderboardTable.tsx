import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { formatPaise } from "../lib/api";
import type { LeaderboardResponse } from "../types";
import { useAuthStore } from "../store/auth";
import { BidModal } from "./BidModal";
import { LiveBadge } from "./LiveBadge";

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
    selected && !selectedIsLeader ? leaderTotal - selected.total_paise + 100 : null;

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
            <div className="rank-main">
              <h2 className="rank-name">
                <Link to={`/projects/${row.project_id}`} style={{ textDecoration: "none", color: "inherit" }}>
                  {row.name}
                </Link>
                <span className="badges">
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
        <p className="empty-state">No live projects yet - submit one and take #1 for ₹1.</p>
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
