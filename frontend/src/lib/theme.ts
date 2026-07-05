import { useCallback, useEffect, useRef, useState } from "react";
import { STORAGE_KEYS, THEME, type ThemeValue } from "./constants";

function readInitial(): ThemeValue {
  if (typeof window === "undefined") return THEME.light;
  try {
    const stored = window.localStorage.getItem(STORAGE_KEYS.theme);
    if (stored === THEME.light || stored === THEME.dark) return stored;
  } catch {
    // localStorage blocked (Safari private mode, cookies disabled) — fall back
    // to the light default.
  }
  return THEME.light;
}

function applyToDom(theme: ThemeValue) {
  const root = document.documentElement;
  root.classList.toggle("dark", theme === THEME.dark);
  root.style.colorScheme = theme;
}

function persist(theme: ThemeValue) {
  try {
    window.localStorage.setItem(STORAGE_KEYS.theme, theme);
  } catch {
    // Same fallback as readInitial — safe to ignore.
  }
}

export function useTheme() {
  const [theme, setThemeState] = useState<ThemeValue>(readInitial);
  const firstMount = useRef(true);

  useEffect(() => {
    applyToDom(theme);
    if (firstMount.current) {
      // Skip persistence on the initial mount so we don't overwrite an empty
      // storage slot with a default the user never picked — preserves the
      // "user has no preference" signal for a future prefers-color-scheme.
      firstMount.current = false;
      return;
    }
    persist(theme);
  }, [theme]);

  const setTheme = useCallback((next: ThemeValue) => setThemeState(next), []);
  const toggle = useCallback(
    () => setThemeState((t) => (t === THEME.dark ? THEME.light : THEME.dark)),
    [],
  );

  return { theme, setTheme, toggle };
}
