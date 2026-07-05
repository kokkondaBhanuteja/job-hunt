import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ErrorView } from "../components/ErrorView";
import { api, getApiBase, getToken, setConfig } from "../lib/api";
import { DEFAULT_API_BASE, QUERY_KEYS } from "../lib/constants";
import { ApplicantPanel } from "./ApplicantPanel";
import { ContextPanel } from "./ContextPanel";
import { SearchPrefsPanel } from "./SearchPrefsPanel";

export function Settings() {
  const qc = useQueryClient();
  const [base, setBase] = useState(getApiBase());
  const [token, setToken] = useState(getToken());
  const [saved, setSaved] = useState(false);

  const health = useQuery({ queryKey: QUERY_KEYS.health, queryFn: api.health, retry: false });
  const profiles = useQuery({ queryKey: QUERY_KEYS.profiles, queryFn: api.profiles, enabled: !!getToken() });

  const [pName, setPName] = useState("");
  const [pKeywords, setPKeywords] = useState("");
  const [pLocation, setPLocation] = useState("");
  const [pPages, setPPages] = useState(1);

  const addProfile = useMutation({
    mutationFn: () =>
      api.addProfile({ name: pName, keywords: pKeywords, location: pLocation, pages: pPages }),
    onSuccess: () => {
      setPName("");
      setPKeywords("");
      setPLocation("");
      qc.invalidateQueries({ queryKey: QUERY_KEYS.profiles });
    },
  });
  const toggle = useMutation({
    mutationFn: (v: { id: number; enabled: boolean }) => api.setProfileEnabled(v.id, v.enabled),
    onSuccess: () => qc.invalidateQueries({ queryKey: QUERY_KEYS.profiles }),
  });

  function save() {
    setConfig(base.trim(), token.trim());
    setSaved(true);
    qc.invalidateQueries();
    setTimeout(() => setSaved(false), 1500);
  }

  return (
    <div className="page">
      <h1>Settings</h1>

      <section className="card-block">
        <h2>Connection</h2>
        <label>
          API base
          <input value={base} onChange={(e) => setBase(e.target.value)} placeholder={DEFAULT_API_BASE} />
        </label>
        <label>
          API token
          <input value={token} onChange={(e) => setToken(e.target.value)} placeholder="bearer token from `hunt serve-api`" type="password" />
        </label>
        <button className="primary" onClick={save}>
          {saved ? "Saved ✓" : "Save"}
        </button>
        <div className="health">
          {health.isSuccess ? (
            <>
              <span className="pill ok">connected</span>
              <span className="mono">
                datastore={health.data.datastore} · sources={health.data.sources.join(",")}
              </span>
              <div className="mono small">
                {Object.entries(health.data.llm).map(([task, cfg]) => (
                  <div key={task}>
                    {task}: {cfg.provider}/{cfg.model}
                  </div>
                ))}
              </div>
            </>
          ) : (
            <span className="pill bad">not connected</span>
          )}
        </div>
      </section>

      <ContextPanel />

      <ApplicantPanel />

      <SearchPrefsPanel />

      <section className="card-block">
        <h2>Search profiles</h2>
        <div className="profile-add">
          <input placeholder="name" value={pName} onChange={(e) => setPName(e.target.value)} />
          <input placeholder="keywords (e.g. nestjs backend)" value={pKeywords} onChange={(e) => setPKeywords(e.target.value)} />
          <input placeholder="location" value={pLocation} onChange={(e) => setPLocation(e.target.value)} />
          <input type="number" min={1} value={pPages} onChange={(e) => setPPages(Number(e.target.value))} style={{ width: 64 }} />
          <button
            className="primary"
            disabled={!pName || !pKeywords || !pLocation || addProfile.isPending}
            onClick={() => addProfile.mutate()}
          >
            Add
          </button>
        </div>
        {addProfile.isError && <ErrorView error={addProfile.error} />}
        <table className="table">
          <thead>
            <tr>
              <th>#</th>
              <th>Name</th>
              <th>Keywords</th>
              <th>Location</th>
              <th>Pages</th>
              <th>Enabled</th>
            </tr>
          </thead>
          <tbody>
            {(profiles.data ?? []).map((p) => (
              <tr key={p.id}>
                <td>{p.id}</td>
                <td>{p.name}</td>
                <td>{p.keywords}</td>
                <td>{p.location}</td>
                <td>{p.pages}</td>
                <td>
                  <input
                    type="checkbox"
                    checked={!!p.enabled}
                    onChange={(e) => toggle.mutate({ id: p.id, enabled: e.target.checked })}
                  />
                </td>
              </tr>
            ))}
            {profiles.data?.length === 0 && (
              <tr>
                <td colSpan={6} className="muted">
                  No profiles yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}
