/**
 * Translate a raw error thrown by `req()` or a mutation into a short, human,
 * empathetic message that tells the user *what happened* and *what to try*.
 *
 * We inspect message text and any status code we can find; we never surface
 * `TypeError: Failed to fetch` or a bare stack line to the user.
 */

export type ErrorKind =
  | "offline"
  | "auth"
  | "notFound"
  | "conflict"
  | "validation"
  | "rateLimit"
  | "server"
  | "timeout"
  | "unknown";

export interface FriendlyError {
  /** Discriminator so callers can pick a matching icon / illustration. */
  kind: ErrorKind;
  /** Short title for the alert heading. */
  title: string;
  /** One-sentence body copy. */
  message: string;
  /** Optional next step ("Try again", "Open Settings"). */
  hint?: string;
  /** Kept for tooltips / dev logs — not usually rendered. */
  technical: string;
}

const NETWORK_HINTS = [
  "failed to fetch",
  "network error",
  "networkerror",
  "load failed",
  "err_network",
  "err_internet_disconnected",
];

function extractStatus(err: unknown): number | null {
  if (typeof err !== "object" || err === null) return null;
  const anyErr = err as Record<string, unknown>;
  const status = anyErr.status ?? anyErr.statusCode ?? anyErr.code;
  if (typeof status === "number") return status;
  // Match the "<status>: <detail>" prefix that `req()` in api.ts throws.
  // Anchored so unrelated 3-digit numbers inside message bodies (timeouts,
  // job ids, port numbers, …) don't hijack the classification.
  if (anyErr.message && typeof anyErr.message === "string") {
    const m = /^\s*([45]\d\d)\s*:/.exec(anyErr.message);
    if (m) return Number(m[1]);
  }
  return null;
}

function extractMessage(err: unknown): string {
  if (typeof err === "string") return err;
  if (err instanceof Error) return err.message;
  if (typeof err === "object" && err !== null && "message" in err) {
    const m = (err as { message: unknown }).message;
    if (typeof m === "string") return m;
  }
  try {
    return String(err);
  } catch {
    return "unknown error";
  }
}

export function friendlyError(err: unknown): FriendlyError {
  const raw = extractMessage(err);
  const lower = raw.toLowerCase();
  const status = extractStatus(err);

  if (NETWORK_HINTS.some((h) => lower.includes(h))) {
    return {
      kind: "offline",
      title: "Can’t reach the server",
      message:
        "The app couldn’t connect to your job-hunt API. Check that the backend is running and that your API base URL is correct.",
      hint: "Open Settings to verify the API base, or try again in a moment.",
      technical: raw,
    };
  }

  if (status === 401 || status === 403) {
    return {
      kind: "auth",
      title: "Not signed in",
      message:
        "The server rejected the request — your API token is missing or has expired.",
      hint: "Head to Settings and paste a fresh token, then retry.",
      technical: raw,
    };
  }

  if (status === 404) {
    return {
      kind: "notFound",
      title: "Nothing here yet",
      message: "The item you asked for wasn’t found on the server. It may have been removed.",
      technical: raw,
    };
  }

  if (status === 409) {
    return {
      kind: "conflict",
      title: "Conflict",
      message: "That change clashes with the current state on the server.",
      hint: "Reload the page to pick up the latest data, then try again.",
      technical: raw,
    };
  }

  if (status === 422 || status === 400) {
    return {
      kind: "validation",
      title: "That didn’t look right",
      message:
        "The server couldn’t understand the request — one of the values is missing or malformed.",
      hint: "Double-check the form and try again.",
      technical: raw,
    };
  }

  if (status === 429) {
    return {
      kind: "rateLimit",
      title: "Too many requests",
      message: "You’re hitting the API faster than it allows. Slow down and give it a moment.",
      hint: "Wait a few seconds and try again.",
      technical: raw,
    };
  }

  if (status && status >= 500) {
    return {
      kind: "server",
      title: "Server hiccup",
      message:
        "The backend ran into a problem processing that. It’s not something you did wrong.",
      hint: "Try again in a moment — if it keeps happening, check the server logs.",
      technical: raw,
    };
  }

  if (lower.includes("abort") || lower.includes("timeout")) {
    return {
      kind: "timeout",
      title: "That took too long",
      message: "The request timed out before the server answered.",
      hint: "Check your connection and try again.",
      technical: raw,
    };
  }

  return {
    kind: "unknown",
    title: "Something went wrong",
    message:
      "The app hit an unexpected problem. It’s usually fixed by trying again.",
    technical: raw,
  };
}

/** True iff the error looks like a network / can't-reach-server problem. */
export function isOfflineError(err: unknown): boolean {
  const lower = extractMessage(err).toLowerCase();
  return NETWORK_HINTS.some((h) => lower.includes(h));
}
