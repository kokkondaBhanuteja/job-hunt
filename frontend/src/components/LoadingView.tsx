// Shared loading placeholder used by every data-loading view.
// Keep the DOM minimal so pages can drop it into any container.

interface Props {
  label?: string;
}

export function LoadingView({ label = "Loading…" }: Props) {
  return (
    <div className="muted" role="status" aria-live="polite">
      {label}
    </div>
  );
}
