import { useEffect, type ReactNode } from "react";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";

interface Props {
  /** Uppercase label shown in the panel head. */
  title: string;
  onClose: () => void;
  children: ReactNode;
}

/**
 * Responsive detail overlay used by JobPanel + EmailDetail.
 *
 * - Mobile (< md): fixed full-height overlay with a backdrop that dismisses
 *   on tap, plus a global Escape-key handler.
 * - Desktop (md+): static side column, no backdrop (background stays
 *   interactive).
 *
 * Close button is 40×40 (WCAG 2.1 AA touch-target floor per CLAUDE.md rule 16).
 */
export function SidePanel({ title, onClose, children }: Props) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <>
      <button
        type="button"
        aria-label="Close panel"
        onClick={onClose}
        className="fixed inset-0 z-30 bg-background/70 backdrop-blur-sm md:hidden"
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="fixed inset-y-0 right-0 z-40 flex w-full max-w-md flex-col overflow-y-auto border-l border-border bg-card shadow-xl md:static md:z-auto md:w-[24rem] md:shrink-0 md:rounded-lg md:border md:shadow-none"
      >
        <div className="flex items-center justify-between border-b border-border px-4 py-2">
          <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            {title}
          </span>
          <Button
            variant="ghost"
            size="icon"
            className="h-10 w-10"
            aria-label="Close"
            onClick={onClose}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
        {children}
      </aside>
    </>
  );
}
