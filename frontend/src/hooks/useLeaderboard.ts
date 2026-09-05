import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, wsUrl } from "../lib/api";
import type { LeaderboardResponse } from "../types";

const QUERY_KEY = ["leaderboard"];

/** Leaderboard state: React Query owns the data (server state, per
 * docs/04), with the WS push writing straight into the query cache. A
 * polling refetch stays on as the doc04-mandated fallback for WS
 * disconnects, since a WS that dies without firing `onclose` (some proxies
 * do this) would otherwise leave the page silently stale forever. */
export function useLeaderboard() {
  const queryClient = useQueryClient();
  const [justChanged, setJustChanged] = useState<Set<string>>(new Set());
  const previousTotals = useRef<Map<string, number>>(new Map());

  const query = useQuery({
    queryKey: QUERY_KEY,
    queryFn: () => apiFetch<LeaderboardResponse>("/projects/leaderboard"),
    refetchInterval: 8000,
  });

  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectDelay = 1000;
    let closedByCleanup = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;

    function connect() {
      ws = new WebSocket(wsUrl("/ws/leaderboard"));

      ws.onopen = () => {
        reconnectDelay = 1000;
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as LeaderboardResponse;

          const changed = new Set<string>();
          for (const entry of data.rankings) {
            const prev = previousTotals.current.get(entry.project_id);
            if (prev !== undefined && prev !== entry.total_paise) changed.add(entry.project_id);
            previousTotals.current.set(entry.project_id, entry.total_paise);
          }
          if (changed.size > 0) {
            setJustChanged(changed);
            setTimeout(() => setJustChanged(new Set()), 2000);
          }

          queryClient.setQueryData(QUERY_KEY, data);
        } catch {
          // ignore malformed frame
        }
      };

      ws.onclose = () => {
        if (closedByCleanup) return;
        reconnectTimer = setTimeout(connect, reconnectDelay);
        reconnectDelay = Math.min(reconnectDelay * 2, 15000);
      };
    }

    connect();
    return () => {
      closedByCleanup = true;
      clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, [queryClient]);

  return { ...query, justChanged };
}
