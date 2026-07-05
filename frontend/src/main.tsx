import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App } from "./App";
import { ErrorBoundary } from "./ErrorBoundary";
import { STORAGE_KEYS, THEME } from "./lib/constants";
import "./styles.css";

// Apply theme synchronously before React renders to prevent FOUC.
// First-run default is light; user's toggle is persisted to localStorage.
// Guarded against SecurityError in privacy-mode browsers (Safari private,
// third-party cookies blocked, …) — fall back to the light default.
(() => {
  let theme: typeof THEME.light | typeof THEME.dark = THEME.light;
  try {
    const stored = window.localStorage.getItem(STORAGE_KEYS.theme);
    if (stored === THEME.dark) theme = THEME.dark;
  } catch {
    // localStorage not accessible — light default is fine.
  }
  document.documentElement.classList.toggle("dark", theme === THEME.dark);
  document.documentElement.style.colorScheme = theme;
})();

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </ErrorBoundary>
  </React.StrictMode>
);
