import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, formatPaise } from "../lib/api";

interface Mismatch {
  project_id: string;
  cached_total_paise: number;
  ledger_total_paise: number;
  cached_bid_count: number;
  ledger_bid_count: number;
  corrected: boolean;
}

interface ReconciliationReport {
  id: string;
  run_at: string;
  projects_checked: number;
  mismatch_count: number;
  mismatches: Mismatch[];
}

/** docs/04's ReconciliationPanel: "surfaces the nightly job's mismatch
 * report, if any." The nightly schedule itself is external
 * (api/scripts/run_reconciliation.py, cron/APScheduler — see the
 * top-level README); this panel reads the latest report and can also
 * trigger a run on demand for ops/testing. */
export function ReconciliationPanel() {
  const queryClient = useQueryClient();

  const { data } = useQuery({
    queryKey: ["admin", "reconciliation", "latest"],
    queryFn: () => apiFetch<{ report: ReconciliationReport | null }>("/admin/reconciliation/report"),
  });

  const runNow = useMutation({
    mutationFn: () => apiFetch("/admin/reconciliation/run", { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "reconciliation", "latest"] }),
  });

  const report = data?.report;

  return (
    <div>
      <h2>Reconciliation</h2>
      <button onClick={() => runNow.mutate()} disabled={runNow.isPending}>
        {runNow.isPending ? "Running…" : "Run now"}
      </button>

      {!report && <p>No reconciliation run yet.</p>}

      {report && (
        <>
          <p>
            Last run {new Date(report.run_at).toLocaleString()} — checked {report.projects_checked} project(s),
            found {report.mismatch_count} mismatch(es).
          </p>
          {report.mismatch_count > 0 && (
            <table className="leaderboard-table">
              <thead>
                <tr>
                  <th>Project</th>
                  <th>Cached total</th>
                  <th>Ledger total</th>
                  <th>Corrected?</th>
                </tr>
              </thead>
              <tbody>
                {report.mismatches.map((m) => (
                  <tr key={m.project_id}>
                    <td>{m.project_id}</td>
                    <td>{formatPaise(m.cached_total_paise)}</td>
                    <td>{formatPaise(m.ledger_total_paise)}</td>
                    <td>{m.corrected ? "Yes" : "No"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}
