import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ErrorView } from "../components/ErrorView";
import { LoadingView } from "../components/LoadingView";
import { api, getToken } from "../lib/api";
import { QUERY_KEYS } from "../lib/constants";
import { ApplyPolicyView } from "./ApplyPolicyView";

/** Settings section: paste/upload Markdown search preferences → parsed into search profiles + apply policy. */
export function SearchPrefsPanel() {
  const qc = useQueryClient();
  const prefs = useQuery({
    queryKey: QUERY_KEYS.searchPrefs,
    queryFn: api.getSearchPrefs,
    enabled: !!getToken(),
  });
  const policy = useQuery({
    queryKey: QUERY_KEYS.applyPolicy,
    queryFn: api.applyPolicy,
    enabled: !!getToken(),
  });
  const [content, setContent] = useState("");
  const [dirty, setDirty] = useState(false);
  const [profilesCreated, setProfilesCreated] = useState<number | null>(null);

  // Pre-fill from stored prefs once, until the user edits.
  useEffect(() => {
    if (prefs.data && !dirty) {
      setContent(prefs.data.content ?? "");
    }
  }, [prefs.data, dirty]);

  const save = useMutation({
    mutationFn: () => api.setSearchPrefs(content),
    onSuccess: (data) => {
      setDirty(false);
      setProfilesCreated(data.profiles_created ?? null);
      // Invalidate searchPrefs (updated content), profiles (new rows), and applyPolicy (re-parsed from new prefs).
      qc.invalidateQueries({ queryKey: QUERY_KEYS.searchPrefs });
      qc.invalidateQueries({ queryKey: QUERY_KEYS.profiles });
      qc.invalidateQueries({ queryKey: QUERY_KEYS.applyPolicy });
    },
  });

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    // File upload is equivalent to paste: populate textarea so the user can review before saving.
    reader.onload = (ev) => {
      const text = ev.target?.result;
      if (typeof text === "string") {
        setContent(text);
        setDirty(true);
        setProfilesCreated(null);
      }
    };
    reader.readAsText(file);
  }

  return (
    <section className="card-block">
      <h2>Search preferences</h2>
      <p className="muted small">
        Describe what roles/skills and locations to search for — I&apos;ll turn it into search
        profiles below.
      </p>
      {prefs.isError && <ErrorView error={prefs.error} />}
      <label htmlFor="search-prefs-file">Upload .md or .txt</label>
      <input
        id="search-prefs-file"
        type="file"
        accept=".md,.txt"
        onChange={handleFileChange}
      />
      <textarea
        id="search-prefs-input"
        className="context-input"
        rows={10}
        placeholder={"# What I'm looking for\n\nBackend engineer roles (Node/NestJS, Python) in Berlin or remote…"}
        value={content}
        onChange={(e) => {
          setContent(e.target.value);
          setDirty(true);
          setProfilesCreated(null);
        }}
      />
      <button
        className="primary"
        disabled={!content.trim() || save.isPending}
        onClick={() => save.mutate()}
      >
        {save.isPending ? "Parsing…" : !dirty && save.isSuccess ? "Saved ✓" : "Parse & save"}
      </button>
      {save.isError && <ErrorView error={save.error} />}
      {profilesCreated !== null && !save.isError && (
        <div className="mono small">created {profilesCreated} profile{profilesCreated !== 1 ? "s" : ""}</div>
      )}
      {prefs.data?.updated_at && (
        <div className="mono small">last updated {prefs.data.updated_at}</div>
      )}
      <h3>Apply policy</h3>
      {policy.isLoading && <LoadingView />}
      {policy.isError && <ErrorView error={policy.error} />}
      {policy.data && <ApplyPolicyView policy={policy.data} />}
    </section>
  );
}
