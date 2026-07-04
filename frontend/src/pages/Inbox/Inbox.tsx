import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { EmptyView } from "../../components/EmptyView";
import { ErrorView } from "../../components/ErrorView";
import { LoadingView } from "../../components/LoadingView";
import { api } from "../../lib/api";
import { EMAIL_CATEGORY, QUERY_KEYS } from "../../lib/constants";
import { EmailRow } from "./EmailRow";
import { EmailDetail } from "./EmailDetail";

const CATEGORY_OPTIONS = ["", ...Object.values(EMAIL_CATEGORY)];

/** Read-only triaged inbox: filterable email list + detail panel + non-blocking sync. */
export function Inbox() {
  const qc = useQueryClient();
  const [category, setCategory] = useState("");
  const [selected, setSelected] = useState<number | null>(null);

  const emails = useQuery({
    queryKey: [...QUERY_KEYS.emails, category],
    queryFn: () => api.emails(category ? { category } : {}),
  });
  const sync = useMutation({
    mutationFn: api.syncEmails,
    onSuccess: () => qc.invalidateQueries({ queryKey: QUERY_KEYS.emails }),
  });

  return (
    <div className="page">
      <div className="page-head">
        <h1>Inbox</h1>
        <div className="actions">
          <select
            aria-label="Filter by category"
            value={category}
            onChange={(ev) => setCategory(ev.target.value)}
          >
            {CATEGORY_OPTIONS.map((c) => (
              <option key={c || "all"} value={c}>
                {c ? c.replace(/_/g, " ") : "All categories"}
              </option>
            ))}
          </select>
          <button className="primary" disabled={sync.isPending} onClick={() => sync.mutate()}>
            {sync.isPending ? "Syncing…" : "Sync inbox"}
          </button>
        </div>
      </div>
      {sync.isError && <ErrorView error={sync.error} />}

      <div className="inbox-layout">
        <div className="inbox-list">
          {emails.isError ? (
            <ErrorView error={emails.error} />
          ) : !emails.data ? (
            <LoadingView label="Loading inbox…" />
          ) : emails.data.length === 0 ? (
            <EmptyView>No emails yet — hit “Sync inbox”.</EmptyView>
          ) : (
            emails.data.map((e) => (
              <EmailRow
                key={e.id}
                email={e}
                active={e.id === selected}
                onSelect={() => setSelected(e.id)}
              />
            ))
          )}
        </div>
        {selected != null && <EmailDetail id={selected} onClose={() => setSelected(null)} />}
      </div>
    </div>
  );
}
