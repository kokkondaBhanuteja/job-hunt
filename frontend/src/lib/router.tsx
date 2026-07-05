// Minimal dependency-free router built on the History API. Clean URLs
// (/board, /board/42, /settings, …) — no `#`. Requires the server to
// SPA-fallback unknown paths to index.html (see nginx.conf.template).
import {
  useSyncExternalStore,
  type AnchorHTMLAttributes,
  type MouseEvent,
} from "react";
import { ROUTES, SCREEN } from "./constants";

/** Fired whenever WE navigate — `popstate` covers browser back/forward. */
const NAV_EVENT = "spa:navigate";

function readRoute(): string {
  const path = window.location.pathname;
  return path === "/" || path === "" ? ROUTES.board : path;
}

/** Full URL suffix (path + query + hash) — used to guard against redundant navigations. */
function currentUrlSuffix(): string {
  return window.location.pathname + window.location.search + window.location.hash;
}

function subscribe(cb: () => void) {
  window.addEventListener("popstate", cb);
  window.addEventListener(NAV_EVENT, cb);
  return () => {
    window.removeEventListener("popstate", cb);
    window.removeEventListener(NAV_EVENT, cb);
  };
}

/** The current pathname, kept in sync with browser navigation. */
export function useRoute(): string {
  return useSyncExternalStore(subscribe, readRoute, readRoute);
}

/**
 * Push a new URL and notify subscribers. Compares the full URL (path + query
 * + hash) so callers can navigate to the same pathname with cleared query
 * state — a plain-pathname compare would silently no-op that case.
 */
export function navigate(path: string): void {
  if (currentUrlSuffix() === path) return;
  window.history.pushState({}, "", path);
  window.dispatchEvent(new Event(NAV_EVENT));
}

function shouldIntercept(e: MouseEvent<HTMLAnchorElement>): boolean {
  if (e.defaultPrevented) return false;
  if (e.button !== 0) return false;
  if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return false;
  const target = e.currentTarget.target;
  if (target && target !== "_self") return false;
  return true;
}

/** Anchor props MINUS href (we own href via the `to` prop). */
type AnchorProps = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href">;
export interface LinkProps extends AnchorProps {
  to: string;
}

/**
 * Anchor that renders a real `href` (right-click / cmd-click / a11y tools work)
 * but intercepts plain left-clicks to route without a page reload. Passes
 * through every standard anchor prop (target, rel, download, title, id, …)
 * so it's a drop-in replacement for `<a>`.
 */
export function Link({ to, onClick, children, ...rest }: LinkProps) {
  return (
    <a
      href={to}
      onClick={(e) => {
        onClick?.(e);
        if (!shouldIntercept(e)) return;
        e.preventDefault();
        navigate(to);
      }}
      {...rest}
    >
      {children}
    </a>
  );
}

/** First path segment → the active screen. "/board/12" → "board". */
export function screenOf(route: string): string {
  return route.split("/").filter(Boolean)[0] ?? SCREEN.board;
}

/** The selected job id from a "/board/<id>" route, else null. */
export function jobIdOf(route: string): number | null {
  const parts = route.split("/").filter(Boolean);
  if (parts[0] === SCREEN.board && parts[1] && /^\d+$/.test(parts[1])) return Number(parts[1]);
  return null;
}

/**
 * Deprecated alias — kept during the hash-router → clean-URL transition.
 * @deprecated Use `useRoute`.
 */
export { useRoute as useHashRoute };

// One-time redirect for users landing on a legacy hash URL. Only fires when
// the pathname is root — otherwise the hash was decorative on a real page and
// replacing the URL would discard where the user actually was.
if (
  typeof window !== "undefined" &&
  (window.location.pathname === "/" || window.location.pathname === "") &&
  window.location.hash.startsWith("#/")
) {
  const legacy = window.location.hash.slice(1);
  window.history.replaceState({}, "", legacy || ROUTES.board);
}
