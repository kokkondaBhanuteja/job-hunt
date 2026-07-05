import { Plus, FileText, FileX } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EmptyView } from "@/components/EmptyView";
import type { VariantSummary } from "@/lib/api";

interface Props {
  variants: VariantSummary[];
  selectedSlug: string | null;
  onSelect: (slug: string) => void;
  onNew: () => void;
}

export function VariantList({ variants, selectedSlug, onSelect, onNew }: Props) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between pb-1">
        <span className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Variants
        </span>
        <Button
          size="sm"
          variant="outline"
          onClick={onNew}
          aria-label="Create new résumé variant"
          className="h-7 gap-1 px-2 text-xs"
        >
          <Plus className="h-3.5 w-3.5" />
          New
        </Button>
      </div>

      {variants.length === 0 ? (
        <EmptyView>No résumé variants yet — click New to add one.</EmptyView>
      ) : (
        <div className="flex flex-col divide-y divide-border overflow-hidden rounded-lg border border-border">
          {variants.map((v) => (
            <button
              key={v.slug}
              className={
                "flex items-center gap-2 px-3 py-2.5 text-left text-sm transition-colors hover:bg-secondary/70 " +
                (selectedSlug === v.slug ? "bg-secondary" : "")
              }
              onClick={() => onSelect(v.slug)}
              aria-pressed={selectedSlug === v.slug}
            >
              {v.has_body ? (
                <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
              ) : (
                <FileX className="h-3.5 w-3.5 shrink-0 text-muted-foreground/50" aria-hidden />
              )}
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium">{v.slug}</div>
                {v.company && (
                  <div className="truncate text-xs text-muted-foreground">{v.company}</div>
                )}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
