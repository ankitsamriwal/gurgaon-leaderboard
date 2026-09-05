import { useEffect, useState } from "react";
import { useLeaderboard } from "../hooks/useLeaderboard";
import { LeaderboardTable } from "../components/LeaderboardTable";
import { Disclaimer } from "../components/Disclaimer";

function leaderClock(iso: string): string {
  const ms = Math.max(0, Date.now() - new Date(iso).getTime());
  const s = Math.floor(ms / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h}h ${String(m).padStart(2, "0")}m ${String(sec).padStart(2, "0")}s`;
  return `${m}m ${String(sec).padStart(2, "0")}s`;
}

export function LeaderboardPage() {
  const { data, isLoading, isError, justChanged } = useLeaderboard();
  const [, setTick] = useState(0);

  // 1s heartbeat so the leader-since clock visibly ticks (live feel).
  useEffect(() => {
    const t = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, []);

  return (
    <div>
      <header className="hero">
        <p className="eyebrow">Gurgaon · Pay-to-rank · Mock payments</p>
        <h1>
          Who tops <em>Gurgaon</em> today?
        </h1>
        <p className="sub">
          A public leaderboard for Gurgaon real estate projects. Every bid raises the
          project's total - outbid the leader's cumulative total by just ₹1 and the
          crown moves. Rank is the bid, nothing else.
        </p>
        <div className="stat-line">
          <span>
            <span className="live-dot">●</span> <b>Live</b> - updates the second a bid lands
          </span>
          {data?.leader && (
            <span>
              Leader for <b>{leaderClock(data.leader.leader_since)}</b>
            </span>
          )}
          {data?.daily_topper && (
            <span>
              Today's top mover: <b>₹{(data.daily_topper.last_24h_paise / 100).toLocaleString("en-IN")}</b> in 24h
            </span>
          )}
        </div>
      </header>
      {isLoading && <p>Loading…</p>}
      {isError && <p role="alert">Could not load the leaderboard. Retrying…</p>}
      {data && <LeaderboardTable data={data} justChanged={justChanged} />}
      <Disclaimer />
    </div>
  );
}
