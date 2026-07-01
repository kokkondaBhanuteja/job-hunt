import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";

export function Runs() {
  const qc = useQueryClient();
  const runs = useQuery({ queryKey: ["runs"], queryFn: api.runs, refetchInterval: 4000 });

  const discover = useMutation({
    mutationFn: api.discover,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["runs"] }),
  });
  const score = useMutation({
    mutationFn: api.score,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["runs"] }),
  });

  return (
    <div className="page">
      <div className="page-head">
        <h1>Runs</h1>
        <div className="actions">
          <button className="primary" disabled={discover.isPending} onClick={() => discover.mutate()}>
            {discover.isPending ? "Starting…" : "Discover now"}
          </button>
          <button disabled={score.isPending} onClick={() => score.mutate()}>
            {score.isPending ? "Starting…" : "Score pending"}
          </button>
        </div>
      </div>
      {(discover.isError || score.isError) && (
        <div className="banner error">{String(discover.error || score.error)}</div>
      )}

      {runs.isError && <div className="banner error">{String(runs.error)}</div>}
      <table className="table">
        <thead>
          <tr>
            <th>#</th>
            <th>Status</th>
            <th>Found</th>
            <th>New</th>
            <th>Started</th>
            <th>Log</th>
          </tr>
        </thead>
        <tbody>
          {(runs.data ?? []).map((r) => (
            <tr key={r.id}>
              <td>{r.id}</td>
              <td>
                <span className={`pill run-${r.status}`}>{r.status}</span>
              </td>
              <td>{r.jobs_found}</td>
              <td>{r.jobs_new}</td>
              <td className="mono">{(r.started_at ?? "").slice(0, 19)}</td>
              <td className="log">{r.log?.trim().split("\n").slice(-1)[0]}</td>
            </tr>
          ))}
          {runs.data?.length === 0 && (
            <tr>
              <td colSpan={6} className="muted">
                No runs yet — hit “Discover now”.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
