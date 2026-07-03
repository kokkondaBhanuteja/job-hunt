// Minimal dependency-free hash router. For a handful of screens this gives what routing is
// actually for — deep links, browser back/forward, shareable URLs — without pulling in
// react-router. Routes: #/board · #/board/<jobId> · #/runs · #/analytics · #/settings.
import { useEffect, useState } from "react";
import { ROUTES, SCREEN } from "./constants";

const DEFAULT_HASH = `#${ROUTES.board}`;

export function useHashRoute(): string {
  const read = () => (window.location.hash || DEFAULT_HASH).replace(/^#/, "");
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const onChange = () => setRoute(read());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

export function navigate(path: string): void {
  window.location.hash = path;
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
