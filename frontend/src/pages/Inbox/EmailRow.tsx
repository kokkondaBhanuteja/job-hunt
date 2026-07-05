import type { EmailSummary } from "@/lib/api";
import { Badge } from "@/components/ui/badge";

interface Props {
  email: EmailSummary;
  active: boolean;
  onSelect: () => void;
}

/** One selectable email in the inbox list: category chip, subject, sender, date. */
export function EmailRow({ email, active, onSelect }: Props) {
  return (
    <button
      onClick={onSelect}
      aria-current={active ? "true" : undefined}
      className={
        "w-full rounded-lg border bg-card p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring " +
        (active
          ? "border-primary/60 bg-secondary/40"
          : "border-border hover:border-primary/40 hover:bg-secondary/30")
      }
    >
      <div className="flex items-center justify-between gap-2">
        <Badge variant="secondary" className="font-normal">
          {(email.category ?? "uncategorized").replace(/_/g, " ")}
        </Badge>
        <span className="font-mono text-[11px] text-muted-foreground">
          {(email.received_at ?? "").slice(0, 10)}
        </span>
      </div>
      <div className="mt-1.5 line-clamp-1 text-sm font-semibold">
        {email.subject ?? "(no subject)"}
      </div>
      <div className="mt-0.5 line-clamp-1 text-xs text-muted-foreground">
        {email.from_name ?? email.from_addr ?? "unknown sender"}
      </div>
    </button>
  );
}
