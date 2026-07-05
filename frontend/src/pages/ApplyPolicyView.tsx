import type { ReactNode } from "react";
import type { ApplyPolicy } from "@/lib/api";
import { EmptyView } from "@/components/EmptyView";
import { Badge } from "@/components/ui/badge";

interface Props {
  policy: ApplyPolicy;
}

/** Read-only display of the parsed apply policy returned by the backend. */
export function ApplyPolicyView({ policy }: Props) {
  const isEmpty =
    policy.must_have.length === 0 && policy.avoid.length === 0 && !policy.seniority;

  if (isEmpty) {
    return (
      <EmptyView icon={null}>
        No apply policy parsed yet — save preferences above to generate one.
      </EmptyView>
    );
  }

  return (
    <div className="space-y-3">
      <dl className="divide-y divide-border rounded-md border border-border">
        <PolicyRow label="Min fit score" value={String(policy.min_fit_score)} />
        {policy.seniority && <PolicyRow label="Seniority" value={policy.seniority} />}
        <PolicyRow label="Remote only" value={policy.remote_only ? "Yes" : "No"} />
      </dl>

      {policy.must_have.length > 0 && (
        <PolicySection title="Must have">
          <div className="flex flex-wrap gap-1.5">
            {policy.must_have.map((item) => (
              <Badge key={item} variant="secondary" className="font-normal">
                {item}
              </Badge>
            ))}
          </div>
        </PolicySection>
      )}

      {policy.avoid.length > 0 && (
        <PolicySection title="Avoid">
          <ul className="list-inside list-disc space-y-0.5 text-[13px] leading-relaxed">
            {policy.avoid.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </PolicySection>
      )}
    </div>
  );
}

function PolicyRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[10rem,1fr] gap-3 px-3 py-2 text-xs">
      <dt className="text-muted-foreground">{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function PolicySection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="space-y-1.5">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
      </p>
      {children}
    </div>
  );
}
