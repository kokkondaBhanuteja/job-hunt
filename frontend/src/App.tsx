import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, getToken } from "./api";
import { Analytics } from "./pages/Analytics";
import { Board } from "./pages/Board";
import { Runs } from "./pages/Runs";
import { Settings } from "./pages/Settings";

type Tab = "board" | "runs" | "analytics" | "settings";

export function App() {
  const [tab, setTab] = useState<Tab>(getToken() ? "board" : "settings");
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, retry: false });

  const tabs: { key: Tab; label: string }[] = [
    { key: "board", label: "Board" },
    { key: "runs", label: "Runs" },
    { key: "analytics", label: "Analytics" },
    { key: "settings", label: "Settings" },
  ];

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          job-hunt <span className="brand-sub">Career OS</span>
        </div>
        <nav className="tabs">
          {tabs.map((t) => (
            <button
              key={t.key}
              className={tab === t.key ? "tab active" : "tab"}
              onClick={() => setTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </nav>
        <div className="status">
          {health.isSuccess ? (
            <span className="pill ok">
              {health.data.datastore} · {Object.values(health.data.llm)[0]?.provider}
            </span>
          ) : (
            <span className="pill bad">API offline</span>
          )}
        </div>
      </header>

      <main className="content">
        {!getToken() && tab !== "settings" && (
          <div className="banner">Set your API token in Settings to connect.</div>
        )}
        {tab === "board" && <Board />}
        {tab === "runs" && <Runs />}
        {tab === "analytics" && <Analytics />}
        {tab === "settings" && <Settings />}
      </main>
    </div>
  );
}
