import {
  CircleAlert,
  FileQuestion,
  GitPullRequestClosed,
  KeyRound,
  ServerCrash,
  Timer,
  TimerReset,
  TriangleAlert,
  WifiOff,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { friendlyError, type ErrorKind } from "@/lib/friendlyError";

interface Props {
  error: unknown;
  /** Override the auto-derived title (e.g. "Couldn’t load runs"). */
  title?: string;
}

const ICONS: Record<ErrorKind, LucideIcon> = {
  offline: WifiOff,
  auth: KeyRound,
  notFound: FileQuestion,
  conflict: GitPullRequestClosed,
  validation: CircleAlert,
  rateLimit: TimerReset,
  server: ServerCrash,
  timeout: Timer,
  unknown: TriangleAlert,
};

/**
 * User-facing error banner. Never shows the raw error text — it translates
 * common failure modes to human copy and picks a matching icon per kind.
 */
export function ErrorView({ error, title }: Props) {
  const friendly = friendlyError(error);
  const Icon = ICONS[friendly.kind];
  return (
    <Alert variant="destructive" role="alert">
      <Icon className="h-4 w-4" />
      <AlertTitle>{title ?? friendly.title}</AlertTitle>
      <AlertDescription className="space-y-1">
        <p>{friendly.message}</p>
        {friendly.hint && <p className="text-xs opacity-80">{friendly.hint}</p>}
      </AlertDescription>
    </Alert>
  );
}
