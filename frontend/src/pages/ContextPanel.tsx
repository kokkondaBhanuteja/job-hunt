import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ErrorView } from "../components/ErrorView";
import { api, getToken } from "../lib/api";
import { QUERY_KEYS } from "../lib/constants";

const FORMATS = ["md", "json"] as const;

/** Settings section: the user's career context, injected into every AI prompt. */
export function ContextPanel() {
  const qc = useQueryClient();
  const ctx = useQuery({
    queryKey: QUERY_KEYS.context,
    queryFn: api.getContext,
    enabled: !!getToken(),
  });
  const [content, setContent] = useState("");
  const [format, setFormat] = useState<string>("md");
  const [dirty, setDirty] = useState(false);

  // Pre-fill from the stored context once, until the user edits.
  useEffect(() => {
    if (ctx.data && !dirty) {
      setContent(ctx.data.content ?? "");
      if (ctx.data.format) setFormat(ctx.data.format);
    }
  }, [ctx.data, dirty]);

  const save = useMutation({
    mutationFn: () => api.setContext({ content, format }),
    onSuccess: () => {
      setDirty(false);
      qc.invalidateQueries({ queryKey: QUERY_KEYS.context });
    },
  });

  return (
    <section className="card-block">
      <h2>Career context</h2>
      <p className="muted small">
        Paste your résumé/context (Markdown or JSON). It is injected into every AI score,
        tailor, cover letter, and review — so the AI always knows you.
      </p>
      {ctx.isError && <ErrorView error={ctx.error} />}
      <label>
        Format
        <select
          value={format}
          onChange={(e) => {
            setFormat(e.target.value);
            setDirty(true);
          }}
        >
          {FORMATS.map((f) => (
            <option key={f} value={f}>
              {f}
            </option>
          ))}
        </select>
      </label>
      <textarea
        className="context-input"
        rows={12}
        placeholder="# About me&#10;&#10;Backend engineer, 2y Node/NestJS + Postgres…"
        value={content}
        onChange={(e) => {
          setContent(e.target.value);
          setDirty(true);
        }}
      />
      <button
        className="primary"
        disabled={!content.trim() || save.isPending}
        onClick={() => save.mutate()}
      >
        {save.isPending ? "Saving…" : !dirty && save.isSuccess ? "Saved ✓" : "Save context"}
      </button>
      {save.isError && <ErrorView error={save.error} />}
      {ctx.data?.updated_at && (
        <div className="mono small">last updated {ctx.data.updated_at}</div>
      )}
    </section>
  );
}
