import type { ReactNode } from "react";
import { Inbox } from "lucide-react";

interface Props {
  children: ReactNode;
  /** Override the default inbox icon (or hide with null). */
  icon?: ReactNode | null;
}

export function EmptyView({ children, icon }: Props) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border/70 px-6 py-10 text-center text-sm text-muted-foreground">
      {icon === undefined ? <Inbox className="h-6 w-6 opacity-60" aria-hidden /> : icon}
      <div>{children}</div>
    </div>
  );
}
