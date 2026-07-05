import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ErrorView } from "../components/ErrorView";
import { api, getToken } from "../lib/api";
import { QUERY_KEYS } from "../lib/constants";

/** Settings section: paste Markdown search preferences → parsed into search profiles. */
export function SearchPrefsPanel() {
  const qc = useQueryClient();
  const prefs = useQuery({
    queryKey: QUERY_KEYS.searchPrefs,
    queryFn: api.getSearchPrefs,
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
      // Invalidate both searchPrefs (updated content) and profiles (new rows added).
      qc.invalidateQueries({ queryKey: QUERY_KEYS.searchPrefs });
      qc.invalidateQueries({ queryKey: QUERY_KEYS.profiles });
    },
  });

  return (
    <section className="card-block">
      <h2>Search preferences</h2>
      <p className="muted small">
        Describe what roles/skills and locations to search for — I&apos;ll turn it into search
        profiles below.
      </p>
      {prefs.isError && <ErrorView error={prefs.error} />}
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
    </section>
  );
}
