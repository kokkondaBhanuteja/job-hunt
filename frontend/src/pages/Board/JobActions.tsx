import type { ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { EmptyView } from "@/components/EmptyView";
import { ErrorView } from "@/components/ErrorView";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api, type ReviewResult } from "@/lib/api";
import { MESSAGE_KIND_LABELS, MESSAGE_KINDS, QUERY_KEYS, type MessageKind } from "@/lib/constants";
import { BriefPanel } from "./BriefPanel";

const SEVERITY_STYLES: Record<string, string> = {
  blocker: "border-l-destructive",
  warning: "border-l-amber-500",
  nit: "border-l-muted-foreground",
};

export function JobActions({ jobId }: { jobId: number }) {
  const qc = useQueryClient();
  const drafts = useQuery({ queryKey: QUERY_KEYS.drafts(jobId), queryFn: () => api.drafts(jobId) });

  const tailor = useMutation({ mutationFn: () => api.tailor(jobId) });
  const cover = useMutation({
    mutationFn: () => api.cover(jobId),
    onSuccess: () => qc.invalidateQueries({ queryKey: QUERY_KEYS.drafts(jobId) }),
  });
  const review = useMutation({ mutationFn: () => api.review(jobId, cover.data?.body ?? "") });
  const fill = useMutation({ mutationFn: () => api.fillJob(jobId) });
  const draftMsg = useMutation({
    mutationFn: (kind: MessageKind) => api.draftMessage(jobId, kind),
    onSuccess: () => qc.invalidateQueries({ queryKey: QUERY_KEYS.drafts(jobId) }),
  });
  const brief = useMutation({ mutationFn: () => api.jobBrief(jobId) });

  const err = tailor.error || cover.error || review.error || fill.error || draftMsg.error || brief.error;

  return (
    <div className="space-y-4">
      <ActionGroup title="Prepare application">
        <Button size="sm" onClick={() => tailor.mutate()} disabled={tailor.isPending}>
          {tailor.isPending ? "Tailoring…" : "Tailor resume"}
        </Button>
        <Button size="sm" variant="outline" onClick={() => cover.mutate()} disabled={cover.isPending}>
          {cover.isPending ? "Writing…" : "Cover letter"}
        </Button>
        <Button size="sm" variant="outline" onClick={() => review.mutate()} disabled={review.isPending}>
          {review.isPending ? "Reviewing…" : "AI review"}
        </Button>
        <Button size="sm" variant="outline" onClick={() => fill.mutate()} disabled={fill.isPending}>
          {fill.isPending ? "Launching…" : "Auto-fill form"}
        </Button>
      </ActionGroup>

      {err && <ErrorView error={err} />}

      <ActionGroup title="Message drafts">
        {MESSAGE_KINDS.map((kind) => (
          <Button
            key={kind}
            size="sm"
            variant="outline"
            onClick={() => draftMsg.mutate(kind)}
            disabled={draftMsg.isPending}
          >
            {draftMsg.isPending && draftMsg.variables === kind ? "Writing…" : MESSAGE_KIND_LABELS[kind]}
          </Button>
        ))}
      </ActionGroup>

      <ActionGroup title="Interview prep">
        <Button size="sm" variant="outline" onClick={() => brief.mutate()} disabled={brief.isPending}>
          {brief.isPending ? "Preparing…" : "Prep brief"}
        </Button>
      </ActionGroup>

      {fill.isSuccess && (
        <div className="text-sm text-emerald-600 dark:text-emerald-400">
          Opening browser — review &amp; submit there.
        </div>
      )}

      {tailor.data && (
        <DraftAccordion title={`Tailored resume · ${tailor.data.variant}`} body={tailor.data.content} />
      )}
      {cover.data && <DraftAccordion title="Cover letter" body={cover.data.body} defaultOpen />}
      {review.data && <ReviewVerdict result={review.data} />}
      {draftMsg.data && (
        <DraftAccordion
          title={`Draft · ${MESSAGE_KIND_LABELS[draftMsg.data.kind] ?? draftMsg.data.kind}`}
          body={draftMsg.data.body}
          defaultOpen
        />
      )}
      {brief.data && <BriefPanel brief={brief.data} />}
      {(drafts.data ?? []).length > 0 && (
        <div className="text-xs text-muted-foreground">{drafts.data!.length} saved draft(s)</div>
      )}
    </div>
  );
}

function ActionGroup({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="space-y-1.5">
      <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
      </h3>
      <div className="flex flex-wrap gap-1.5">{children}</div>
    </div>
  );
}

function DraftAccordion({ title, body, defaultOpen }: { title: string; body: string; defaultOpen?: boolean }) {
  return (
    <details open={defaultOpen} className="group rounded-md border border-border bg-secondary/40">
      <summary className="cursor-pointer select-none px-3 py-2 text-sm font-medium marker:text-muted-foreground">
        {title}
      </summary>
      <pre className="max-h-60 overflow-auto whitespace-pre-wrap border-t border-border px-3 py-2 text-xs leading-relaxed text-foreground/90">
        {body}
      </pre>
    </details>
  );
}

function ReviewVerdict({ result }: { result: ReviewResult }) {
  return (
    <div className="space-y-2">
      <div>
        {result.ready ? (
          <Badge className="bg-emerald-500/15 text-emerald-600 hover:bg-emerald-500/20 dark:text-emerald-400">
            ready to submit · ATS: {result.ats}
          </Badge>
        ) : (
          <Badge variant="destructive">needs work · ATS: {result.ats}</Badge>
        )}
      </div>
      {result.issues.length === 0 ? (
        <EmptyView icon={null}>No issues flagged.</EmptyView>
      ) : (
        <ul className="space-y-1.5">
          {result.issues.map((issue, i) => (
            <li
              key={i}
              className={
                "rounded-md border-l-4 bg-secondary/40 px-2.5 py-1.5 text-xs leading-relaxed " +
                (SEVERITY_STYLES[issue.severity] ?? "border-l-border")
              }
            >
              <b className="uppercase tracking-wide">{issue.severity}</b>
              {issue.field ? ` (${issue.field})` : ""} — {issue.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
