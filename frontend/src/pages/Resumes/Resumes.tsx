import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { FileEdit } from "lucide-react";
import { EmptyView } from "@/components/EmptyView";
import { ErrorView } from "@/components/ErrorView";
import { LoadingView } from "@/components/LoadingView";
import { api } from "@/lib/api";
import { QUERY_KEYS } from "@/lib/constants";
import { VariantEditor } from "./VariantEditor";
import { VariantList } from "./VariantList";

/** Discriminated state: nothing selected, new-variant form, or editing an existing slug. */
type EditorState = { mode: "none" } | { mode: "new" } | { mode: "edit"; slug: string };

export function Resumes() {
  const [editorState, setEditorState] = useState<EditorState>({ mode: "none" });

  const variants = useQuery({
    queryKey: QUERY_KEYS.variants,
    queryFn: api.variants,
  });

  function handleSaved(slug: string) {
    setEditorState({ mode: "edit", slug });
  }

  if (variants.isLoading) return <LoadingView label="Loading résumé variants…" />;
  if (variants.isError) return <ErrorView error={variants.error} />;

  const list = variants.data ?? [];

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold tracking-tight">Résumés</h1>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-[260px_1fr]">
        <VariantList
          variants={list}
          selectedSlug={editorState.mode === "edit" ? editorState.slug : null}
          onSelect={(slug) => setEditorState({ mode: "edit", slug })}
          onNew={() => setEditorState({ mode: "new" })}
        />

        <div className="min-w-0">
          {editorState.mode === "none" && (
            <EmptyView icon={<FileEdit className="h-6 w-6 opacity-60" aria-hidden />}>
              Select a variant from the list or click New to create one.
            </EmptyView>
          )}
          {editorState.mode === "new" && (
            <VariantEditor key="__new__" slug={null} onSaved={handleSaved} />
          )}
          {editorState.mode === "edit" && (
            <VariantEditor
              key={editorState.slug}
              slug={editorState.slug}
              onSaved={handleSaved}
            />
          )}
        </div>
      </div>
    </div>
  );
}
