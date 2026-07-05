import type { RoleBrief } from "@/lib/api";

export function BriefPanel({ brief }: { brief: RoleBrief }) {
  return (
    <div className="space-y-3 rounded-md border border-border bg-secondary/40 p-3">
      {brief.summary && <p className="text-[13px] leading-relaxed">{brief.summary}</p>}
      <BriefSection title="Key skills" items={brief.key_skills} />
      <BriefSection title="Interview topics" items={brief.interview_topics} />
      <BriefSection title="Questions to ask" items={brief.questions_to_ask} />
      {brief.fit_notes && (
        <p className="text-[13px] leading-relaxed text-muted-foreground">{brief.fit_notes}</p>
      )}
    </div>
  );
}

function BriefSection({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div className="space-y-1">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
      </p>
      <ul className="list-inside list-disc space-y-0.5 text-[13px] leading-relaxed">
        {items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </div>
  );
}
