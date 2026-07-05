import { useQuery } from "@tanstack/react-query";
import { ErrorView } from "@/components/ErrorView";
import { LoadingView } from "@/components/LoadingView";
import { SidePanel } from "@/components/SidePanel";
import { Badge } from "@/components/ui/badge";
import { api, type EmailDetail as EmailDetailDto } from "@/lib/api";
import { QUERY_KEYS, ROUTES } from "@/lib/constants";
import { Link } from "@/lib/router";
import { EmailActions } from "./EmailActions";

interface Props {
  id: number;
  onClose: () => void;
}

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

  return (
    <SidePanel title="Email detail" onClose={onClose}>
      {detail.isError ? (
        <div className="p-4">
          <ErrorView error={detail.error} />
        </div>
      ) : !detail.data ? (
        <div className="p-4">
          <LoadingView />
        </div>
      ) : (
        <EmailBody email={detail.data} />
      )}
    </SidePanel>
  );
}

function EmailBody({ email: e }: { email: EmailDetailDto }) {
  const fields = extractedFields(e.extracted);
  return (
    <div className="flex flex-col gap-4 p-4">
      <header className="space-y-1">
        <h2 className="text-lg font-semibold leading-tight tracking-tight">
          {e.subject ?? "(no subject)"}
        </h2>
        <div className="text-xs text-muted-foreground">
          {[e.from_name, e.from_addr].filter(Boolean).join(" · ")}
        </div>
      </header>
      {e.snippet && <p className="text-[13px] leading-relaxed">{e.snippet}</p>}

      <div className="flex flex-wrap gap-1.5">
        {e.job_id != null && (
          <Link
            to={ROUTES.jobDetail(e.job_id)}
            className="inline-flex items-center rounded-md border border-border bg-background px-2 py-0.5 text-xs text-primary hover:bg-secondary"
          >
            Job #{e.job_id}
          </Link>
        )}
        {e.company_id != null && (
          <Badge variant="secondary" className="font-normal">
            Company #{e.company_id}
          </Badge>
        )}
        {e.application_id != null && (
          <Badge variant="secondary" className="font-normal">
            Application #{e.application_id}
          </Badge>
        )}
      </div>

      {fields.length > 0 && (
        <dl className="divide-y divide-border rounded-md border border-border">
          {fields.map(([k, v]) => (
            <div key={k} className="grid grid-cols-[7rem,1fr] gap-3 px-3 py-2 text-xs">
              <dt className="capitalize text-muted-foreground">{k.replace(/_/g, " ")}</dt>
              <dd className="break-words">{v}</dd>
            </div>
          ))}
        </dl>
      )}
      <EmailActions email={e} />
    </div>
  );
}
