import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";

interface Props {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  /** Label for the item type shown in the "Showing …" line. Defaults to "items". */
  itemName?: string;
}

/**
 * Shared pagination bar for every paged list/table.
 * Compact on mobile (Prev / n of N / Next), fuller on md+ (numbered pages + count).
 */
export function Pagination({
  page,
  pageSize,
  total,
  onPageChange,
  itemName = "items",
}: Props) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const clamped = Math.min(Math.max(1, page), totalPages);
  const start = total === 0 ? 0 : (clamped - 1) * pageSize + 1;
  const end = Math.min(clamped * pageSize, total);

  if (total <= pageSize) return null;

  const numbers = pageNumbers(clamped, totalPages);

  return (
    <nav
      role="navigation"
      aria-label="Pagination"
      className="flex flex-wrap items-center justify-between gap-3 pt-1"
    >
      <div className="text-xs text-muted-foreground tabular-nums">
        Showing <span className="text-foreground">{start}</span>&ndash;
        <span className="text-foreground">{end}</span> of{" "}
        <span className="text-foreground">{total}</span> {itemName}
      </div>

      <div className="flex items-center gap-1">
        <Button
          variant="outline"
          size="sm"
          className="h-8 px-2"
          onClick={() => onPageChange(clamped - 1)}
          disabled={clamped <= 1}
          aria-label="Previous page"
        >
          <ChevronLeft className="h-4 w-4" />
          <span className="hidden sm:inline">Prev</span>
        </Button>

        <div className="hidden items-center gap-1 sm:flex">
          {numbers.map((n, i) =>
            n === "…" ? (
              <span
                key={`gap-${i}`}
                className="px-1 text-xs text-muted-foreground"
                aria-hidden
              >
                …
              </span>
            ) : (
              <Button
                key={n}
                variant={n === clamped ? "default" : "outline"}
                size="sm"
                className="h-8 w-8 p-0 tabular-nums"
                onClick={() => onPageChange(n)}
                aria-current={n === clamped ? "page" : undefined}
                aria-label={`Page ${n}`}
              >
                {n}
              </Button>
            ),
          )}
        </div>

        <span className="px-2 text-xs tabular-nums text-muted-foreground sm:hidden">
          {clamped} / {totalPages}
        </span>

        <Button
          variant="outline"
          size="sm"
          className="h-8 px-2"
          onClick={() => onPageChange(clamped + 1)}
          disabled={clamped >= totalPages}
          aria-label="Next page"
        >
          <span className="hidden sm:inline">Next</span>
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </nav>
  );
}

/** Return the page-number sequence with ellipses. Always shows first/last + a window around current. */
function pageNumbers(current: number, total: number): (number | "…")[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const out: (number | "…")[] = [1];
  const from = Math.max(2, current - 1);
  const to = Math.min(total - 1, current + 1);
  if (from > 2) out.push("…");
  for (let i = from; i <= to; i++) out.push(i);
  if (to < total - 1) out.push("…");
  out.push(total);
  return out;
}

/** Pure helper — slice an array to the current page. Same source of truth for tests. */
export function paginate<T>(items: readonly T[], page: number, pageSize: number): T[] {
  const totalPages = Math.max(1, Math.ceil(items.length / pageSize));
  const clamped = Math.min(Math.max(1, page), totalPages);
  return items.slice((clamped - 1) * pageSize, clamped * pageSize);
}
