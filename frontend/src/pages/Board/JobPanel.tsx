import { type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { EmptyView } from "@/components/EmptyView";
import { LoadingView } from "@/components/LoadingView";
import { SidePanel } from "@/components/SidePanel";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { api, type JobDetail, type ScoreRow } from "@/lib/api";
import { QUERY_KEYS } from "@/lib/constants";
import { JobActions } from "./JobActions";
import { LogApplicationForm } from "./LogApplicationForm";
import { NextActionChip } from "./NextActionChip";
import { ScoreExplanationSection } from "./ScoreExplanation";
import { ScoreBadge } from "./ScoreBadge";
import { SimilarJobs } from "./SimilarJobs";

/** The slide-in job detail. Fixed overlay on mobile; inline side column on md+. */
export function JobPanel({ jobId, onClose }: { jobId: number; onClose: () => void }) {
  const detail = useQuery({ queryKey: QUERY_KEYS.job(jobId), queryFn: () => api.job(jobId) });

  return (
    <SidePanel title="Job detail" onClose={onClose}>
      {!detail.data ? (
        <div className="p-4">
          <LoadingView />
        </div>
      ) : (
        <div className="flex flex-col gap-5 p-4">
          <JobHeader job={detail.data.job} />
          <NextActionChip jobId={jobId} />
          <Section title="Scores">
            <ScoreList scores={detail.data.scores} />
            <ScoreExplanationSection jobId={jobId} />
          </Section>
          <Section title="Job description">
            <pre className="max-h-60 overflow-auto whitespace-pre-wrap rounded-md border border-border bg-secondary/50 p-3 text-xs leading-relaxed text-foreground/90">
              {detail.data.job.description || "(no description captured yet)"}
            </pre>
          </Section>
          <SimilarJobs jobId={jobId} />
          <Separator />
          <JobActions jobId={jobId} />
          <Separator />
          <Section title="Log application">
            <LogApplicationForm
              jobId={jobId}
              variantOptions={detail.data.scores.map((s) => s.variant)}
            />
          </Section>
        </div>
      )}
    </SidePanel>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
      </h3>
      {children}
    </section>
  );
}

function JobHeader({ job }: { job: JobDetail["job"] }) {
  return (
    <header className="space-y-2">
      <h2 className="text-lg font-semibold leading-tight tracking-tight">{job.title}</h2>
      <div className="text-sm text-muted-foreground">
        {job.company}
        {job.location ? ` · ${job.location}` : ""}
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge variant="secondary" className="font-normal">
          {job.state}
        </Badge>
        <a
          className="inline-flex items-center gap-1 rounded-md border border-border bg-background px-2 py-0.5 text-xs text-primary transition-colors hover:bg-secondary"
          href={job.apply_url}
          target="_blank"
          rel="noreferrer"
        >
          open <ExternalLink className="h-3 w-3" />
        </a>
      </div>
    </header>
  );
}

function ScoreList({ scores }: { scores: ScoreRow[] }) {
  if (scores.length === 0) return <EmptyView icon={null}>Not scored yet.</EmptyView>;
  return (
    <div className="space-y-2">
      {scores.map((s) => (
        <div key={s.variant} className="rounded-md border border-border bg-secondary/40 p-3">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold">{s.variant}</span>
            <ScoreBadge score={s.fit_score} />
            {s.confidence != null && (
              <span className="text-[11px] text-muted-foreground">conf {s.confidence}</span>
            )}
          </div>
          <p className="mt-1.5 text-[13px] leading-relaxed text-foreground/90">{s.reasoning}</p>
        </div>
      ))}
    </div>
  );
}

