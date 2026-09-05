import { useLeaderboard } from "../hooks/useLeaderboard";
import { LeaderboardTable } from "../components/LeaderboardTable";
import { Disclaimer } from "../components/Disclaimer";

export function LeaderboardPage() {
  const { data, isLoading, isError, justChanged } = useLeaderboard();

  return (
    <div>
      <h1>Gurgaon Leaderboard</h1>
      <Disclaimer />
      {isLoading && <p>Loading…</p>}
      {isError && <p role="alert">Could not load the leaderboard. Retrying…</p>}
      {data && <LeaderboardTable data={data} justChanged={justChanged} />}
    </div>
  );
}
