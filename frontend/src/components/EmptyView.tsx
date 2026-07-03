// Shared empty-state message used by every data-loading view.
// Children can be text or richer content (e.g. a call-to-action link).

import type { ReactNode } from "react";

interface Props {
  children: ReactNode;
}

export function EmptyView({ children }: Props) {
  return <div className="muted">{children}</div>;
}
