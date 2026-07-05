import { Skeleton } from "@/components/ui/skeleton";

interface Props {
  label?: string;
  /** How many skeleton bars to render below the label. Defaults to 3. */
  rows?: number;
}

export function LoadingView({ label = "Loading…", rows = 3 }: Props) {
  return (
    <div role="status" aria-live="polite" aria-label={label} className="space-y-3 py-2">
      <div className="text-sm text-muted-foreground">{label}</div>
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className={i === 0 ? "h-4 w-2/3" : "h-4 w-full"} />
      ))}
    </div>
  );
}
