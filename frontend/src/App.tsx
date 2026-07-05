import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Menu, Moon, Sun } from "lucide-react";
import { ErrorBoundary } from "@/ErrorBoundary";
import { OfflineView } from "@/components/OfflineView";
import { api, getToken } from "@/lib/api";
import { QUERY_KEYS, SCREEN, THEME } from "@/lib/constants";
import { Link, screenOf, useRoute } from "@/lib/router";
import { useTheme } from "@/lib/theme";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Analytics } from "@/pages/Analytics";
import { Board } from "@/pages/Board";
import { Content } from "@/pages/Content";
import { Inbox } from "@/pages/Inbox";
import { Runs } from "@/pages/Runs";
import { Settings } from "@/pages/Settings";

const TABS = [
  { key: SCREEN.board, label: "Board" },
  { key: SCREEN.inbox, label: "Inbox" },
  { key: SCREEN.content, label: "Content" },
  { key: SCREEN.runs, label: "Runs" },
  { key: SCREEN.analytics, label: "Analytics" },
  { key: SCREEN.settings, label: "Settings" },
];

export function App() {
  const screen = screenOf(useRoute());
  const { theme, toggle: toggleTheme } = useTheme();
  const health = useQuery({ queryKey: QUERY_KEYS.health, queryFn: api.health, retry: false });
  const auth = useQuery({
    queryKey: QUERY_KEYS.auth,
    queryFn: api.ping,
    retry: false,
  });

  return (
    <div className="flex min-h-full flex-col bg-background text-foreground">
      <header className="sticky top-0 z-40 flex h-14 items-center gap-3 border-b border-border bg-card/95 px-4 backdrop-blur supports-[backdrop-filter]:bg-card/80 md:px-6">
        <div className="flex items-baseline gap-1.5 font-semibold tracking-tight">
          job-hunt
          <span className="hidden text-xs font-medium text-muted-foreground sm:inline">
            Career OS
          </span>
        </div>

        <nav className="ml-2 hidden md:flex md:items-center md:gap-0.5">
          {TABS.map((t) => (
            <Link
              key={t.key}
              to={`/${t.key}`}
              aria-current={screen === t.key ? "page" : undefined}
              className={
                "rounded-md px-3 py-1.5 text-sm transition-colors " +
                (screen === t.key
                  ? "bg-secondary text-foreground"
                  : "text-muted-foreground hover:bg-secondary/70 hover:text-foreground")
              }
            >
              {t.label}
            </Link>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <StatusPill
            healthOk={health.isSuccess}
            authError={!!getToken() && auth.isError}
            summary={
              health.isSuccess
                ? `${health.data.datastore} · ${Object.values(health.data.llm)[0]?.provider}`
                : null
            }
          />
          <Button
            variant="outline"
            size="icon"
            className="h-8 w-8"
            aria-label={theme === THEME.dark ? "Switch to light theme" : "Switch to dark theme"}
            onClick={toggleTheme}
          >
            {theme === THEME.dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>
          <MobileNav screen={screen} />
        </div>
      </header>

      <main className="flex-1">
        <div className="mx-auto w-full max-w-7xl px-4 py-5 md:px-6 md:py-6">
          {health.isError && screen !== SCREEN.settings ? (
            <OfflineView
              onRetry={() => void health.refetch()}
              retrying={health.isFetching}
            />
          ) : (
            <>
              {!getToken() && screen !== SCREEN.settings && (
                <div className="mb-4 rounded-md border border-border bg-secondary px-4 py-3 text-sm">
                  Set your API token in{" "}
                  <Link
                    className="text-primary underline-offset-4 hover:underline"
                    to={`/${SCREEN.settings}`}
                  >
                    Settings
                  </Link>{" "}
                  to connect.
                </div>
              )}
              {/*
                Keyed on the SCREEN (top-level tab), not the full route —
                sub-route changes (e.g. /board → /board/42 when a job card
                opens) shouldn't remount the tree and re-fire every query.
                A caught error still resets when the user switches tabs.
              */}
              <ErrorBoundary key={screen}>
                {screen === SCREEN.board && <Board />}
                {screen === SCREEN.inbox && <Inbox />}
                {screen === SCREEN.content && <Content />}
                {screen === SCREEN.runs && <Runs />}
                {screen === SCREEN.analytics && <Analytics />}
                {screen === SCREEN.settings && <Settings />}
              </ErrorBoundary>
            </>
          )}
        </div>
      </main>
    </div>
  );
}

function StatusPill({
  healthOk,
  authError,
  summary,
}: {
  healthOk: boolean;
  authError: boolean;
  summary: string | null;
}) {
  if (!healthOk) return <Badge variant="destructive">API offline</Badge>;
  if (authError) return <Badge variant="destructive">unauthorized</Badge>;
  return (
    <Badge variant="secondary" className="gap-1.5 font-normal">
      <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" aria-hidden />
      <span className="hidden sm:inline">{summary}</span>
      <span className="sm:hidden">online</span>
    </Badge>
  );
}

function MobileNav({ screen }: { screen: string }) {
  const [open, setOpen] = useState(false);
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="outline" size="icon" className="h-8 w-8 md:hidden" aria-label="Open navigation">
          <Menu className="h-4 w-4" />
        </Button>
      </SheetTrigger>
      <SheetContent side="right" className="w-64">
        <SheetHeader>
          <SheetTitle>Navigate</SheetTitle>
        </SheetHeader>
        <nav className="mt-4 flex flex-col gap-1 px-2">
          {TABS.map((t) => (
            <Link
              key={t.key}
              to={`/${t.key}`}
              aria-current={screen === t.key ? "page" : undefined}
              onClick={() => setOpen(false)}
              className={
                "rounded-md px-3 py-2 text-sm transition-colors " +
                (screen === t.key
                  ? "bg-secondary text-foreground"
                  : "text-muted-foreground hover:bg-secondary/70 hover:text-foreground")
              }
            >
              {t.label}
            </Link>
          ))}
        </nav>
      </SheetContent>
    </Sheet>
  );
}
