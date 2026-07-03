// Shared error banner used by every data-loading view.
// Accepts `unknown` because React Query surfaces errors as `unknown` by default.

interface Props {
  error: unknown;
}

export function ErrorView({ error }: Props) {
  return (
    <div className="banner error" role="alert">
      {String(error)}
    </div>
  );
}
