import { useQuery } from "@tanstack/react-query";
import { ErrorView } from "../../components/ErrorView";
import { LoadingView } from "../../components/LoadingView";
import { api } from "../../lib/api";
import { QUERY_KEYS, ROUTES } from "../../lib/constants";

interface Props {
  id: number;
  onClose: () => void;
}

/** Parse the stored `extracted` JSON string into displayable key/value rows. */
function extractedFields(raw: string | null): [string, string][] {
  if (!raw) return [];
  try {
    const obj = JSON.parse(raw) as Record<string, unknown>;
    return Object.entries(obj).map(([k, v]) => [k, String(v)]);
  } catch {
    return [];
  }
}

/** Side panel: full email detail with LLM-extracted fields and pipeline link chips. */
export function EmailDetail({ id, onClose }: Props) {
  const detail = useQuery({ queryKey: QUERY_KEYS.email(id), queryFn: () => api.emailDetail(id) });

  if (detail.isError) return <aside className="panel"><ErrorView error={detail.error} /></aside>;
  if (!detail.data) return <aside className="panel"><LoadingView /></aside>;

  const e = detail.data;
  const fields = extractedFields(e.extracted);

  return (
    <aside className="panel">
      <div className="panel-head">
        <button className="close" aria-label="Close" onClick={onClose}>✕</button>
      </div>
      <div className="panel-body">
        <h2>{e.subject ?? "(no subject)"}</h2>
        <div className="muted">{[e.from_name, e.from_addr].filter(Boolean).join(" · ")}</div>
        {e.snippet && <p>{e.snippet}</p>}
        <div className="chips">
          {e.job_id != null && (
            <a className="chip link" href={`#${ROUTES.jobDetail(e.job_id)}`}>Job #{e.job_id}</a>
          )}
          {e.company_id != null && <span className="chip">Company #{e.company_id}</span>}
          {e.application_id != null && <span className="chip">Application #{e.application_id}</span>}
        </div>
        {fields.length > 0 && (
          <dl className="kv">
            {fields.map(([k, v]) => (
              <div key={k}>
                <dt>{k.replace(/_/g, " ")}</dt>
                <dd>{v}</dd>
              </div>
            ))}
          </dl>
        )}
      </div>
    </aside>
  );
}
