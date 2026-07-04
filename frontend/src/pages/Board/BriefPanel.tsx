// Renders the RoleBrief returned by POST /api/jobs/{id}/brief.
// Extracted here so JobActions.tsx stays under 150 lines.

import type { RoleBrief } from "../../lib/api";

export function BriefPanel({ brief }: { brief: RoleBrief }) {
  return (
    <div className="brief-panel">
      {brief.summary && <p className="brief-summary">{brief.summary}</p>}
      <BriefSection title="Key skills" items={brief.key_skills} />
      <BriefSection title="Interview topics" items={brief.interview_topics} />
      <BriefSection title="Questions to ask" items={brief.questions_to_ask} />
      {brief.fit_notes && <p className="brief-fit-notes">{brief.fit_notes}</p>}
    </div>
  );
}

function BriefSection({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div className="brief-section">
      <p className="brief-section-title">{title}</p>
      <ul className="brief-list">
        {items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </div>
  );
}
