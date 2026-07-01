import { useQuery } from "@tanstack/react-query";
import { api } from "../api";

const FUNNEL_ORDER = ["applied", "oa", "interview", "hr", "offer", "rejected"];

export function Analytics() {
  const q = useQuery({ queryKey: ["analytics"], queryFn: api.analytics });

  if (q.isError) return <div className="banner error">{String(q.error)}</div>;
  if (!q.data) return <div className="muted">Loading…</div>;
  const d = q.data;
  const funnel = Object.fromEntries(d.funnel.map((f) => [f.stage, f.n]));

  return (
    <div className="page">
      <h1>Analytics</h1>

      <section className="card-block">
        <h2>Application funnel</h2>
        <div className="funnel">
          {FUNNEL_ORDER.map((stage) => (
            <div className="funnel-step" key={stage}>
              <div className="funnel-n">{funnel[stage] ?? 0}</div>
              <div className="funnel-label">{stage}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="card-block">
        <h2>LLM cost</h2>
        <div className="metric-row">
          <Metric label="calls" value={d.llm_cost.calls} />
          <Metric label="tokens" value={d.llm_cost.tokens} />
          <Metric label="cost (USD)" value={`$${Number(d.llm_cost.cost).toFixed(4)}`} />
        </div>
        <MiniTable title="By task" rows={d.llm_by_task.map((t) => [t.task, `${t.calls} calls`, `$${Number(t.cost).toFixed(4)}`])} />
      </section>

      <div className="two-col">
        <section className="card-block">
          <h2>Jobs by state</h2>
          <MiniTable rows={d.jobs_by_state.map((s) => [s.state, String(s.n)])} />
        </section>
        <section className="card-block">
          <h2>Jobs by source</h2>
          <MiniTable rows={d.jobs_by_source.map((s) => [s.source, String(s.n)])} />
        </section>
      </div>

      <section className="card-block">
        <h2>Source effectiveness (applied)</h2>
        <MiniTable rows={d.source_effectiveness.map((s) => [s.source, String(s.applied)])} />
      </section>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="metric">
      <div className="metric-value">{value}</div>
      <div className="metric-label">{label}</div>
    </div>
  );
}

function MiniTable({ title, rows }: { title?: string; rows: string[][] }) {
  return (
    <div className="mini-table">
      {title && <div className="mini-title">{title}</div>}
      {rows.length === 0 && <div className="muted small">no data yet</div>}
      {rows.map((cells, i) => (
        <div className="mini-row" key={i}>
          {cells.map((c, j) => (
            <span key={j} className={j === 0 ? "mini-key" : "mini-val"}>
              {c}
            </span>
          ))}
        </div>
      ))}
    </div>
  );
}
