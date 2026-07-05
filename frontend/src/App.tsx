import { useQuery } from "@tanstack/react-query";
import { api, getToken } from "./lib/api";
import { QUERY_KEYS, SCREEN } from "./lib/constants";
import { screenOf, useHashRoute } from "./lib/router";
import { Analytics } from "./pages/Analytics";
import { Board } from "./pages/Board";
import { Content } from "./pages/Content";
import { Inbox } from "./pages/Inbox";
import { Runs } from "./pages/Runs";
import { Settings } from "./pages/Settings";

const TABS = [
  { key: SCREEN.board, label: "Board" },
  { key: SCREEN.inbox, label: "Inbox" },
  { key: SCREEN.content, label: "Content" },
  { key: SCREEN.runs, label: "Runs" },
  { key: SCREEN.analytics, label: "Analytics" },
  { key: SCREEN.settings, label: "Settings" },
];

export function App() {
  const screen = screenOf(useHashRoute());
  const health = useQuery({ queryKey: QUERY_KEYS.health, queryFn: api.health, retry: false });
  // /health is unauthenticated — probe an authed endpoint so a bad token reads as
  // "unauthorized", not "connected".
  const auth = useQuery({
    queryKey: QUERY_KEYS.auth,
    queryFn: api.ping,
    retry: false,
    enabled: !!getToken(),
  });

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          job-hunt <span className="brand-sub">Career OS</span>
        </div>
        <nav className="tabs">
          {TABS.map((t) => (
            <a key={t.key} href={`#/${t.key}`} className={screen === t.key ? "tab active" : "tab"}>
              {t.label}
            </a>
          ))}
        </nav>
        <div className="status">
          {!health.isSuccess ? (
            <span className="pill bad">API offline</span>
          ) : getToken() && auth.isError ? (
            <span className="pill bad">unauthorized</span>
          ) : (
            <span className="pill ok">
              {health.data.datastore} · {Object.values(health.data.llm)[0]?.provider}
            </span>
          )}
        </div>
      </header>

      <main className="content">
        {!getToken() && screen !== SCREEN.settings && (
          <div className="banner">Set your API token in Settings to connect.</div>
        )}
        {screen === SCREEN.board && <Board />}
        {screen === SCREEN.inbox && <Inbox />}
        {screen === SCREEN.content && <Content />}
        {screen === SCREEN.runs && <Runs />}
        {screen === SCREEN.analytics && <Analytics />}
        {screen === SCREEN.settings && <Settings />}
      </main>
    </div>
  );
}
