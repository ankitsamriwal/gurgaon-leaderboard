import { Link } from "react-router-dom";
import { formatPaise } from "../lib/api";
import type { LeaderboardResponse } from "../types";
import { LiveBadge } from "./LiveBadge";

function leaderSinceLabel(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const hours = Math.floor(ms / 3_600_000);
  if (hours < 1) return "less than an hour";
  const days = Math.floor(hours / 24);
  if (days < 1) return `${hours}h`;
  return `${days}d ${hours % 24}h`;
}

export function LeaderboardTable({
  data,
  justChanged,
}: {
  data: LeaderboardResponse;
  justChanged: Set<string>;
}) {
  return (
    <div className="leaderboard">
      {data.leader && (
        <p className="leaderboard-meta">
          Leader for {leaderSinceLabel(data.leader.leader_since)}
        </p>
      )}
      {data.daily_topper && (
        <p className="leaderboard-meta">
          Today's top mover: {formatPaise(data.daily_topper.last_24h_paise)} in the last 24h
        </p>
      )}

      <table className="leaderboard-table">
        <thead>
          <tr>
            <th>Rank</th>
            <th>Project</th>
            <th>Developer</th>
            <th>Locality</th>
            <th>Total raised</th>
            <th>Bids</th>
          </tr>
        </thead>
        <tbody>
          {data.rankings.map((row) => (
            <tr key={row.project_id} className={justChanged.has(row.project_id) ? "row-live" : undefined}>
              <td>#{row.rank}</td>
              <td>
                <Link to={`/projects/${row.project_id}`}>{row.name}</Link>
                {justChanged.has(row.project_id) && <LiveBadge />}
              </td>
              <td>{row.developer_name}</td>
              <td>{row.locality}</td>
              <td>{formatPaise(row.total_paise)}</td>
              <td>{row.bid_count}</td>
            </tr>
          ))}
          {data.rankings.length === 0 && (
            <tr>
              <td colSpan={6} className="empty-state">
                No live projects yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
