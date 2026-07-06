import { useRef } from "react";
import { useMutation } from "@tanstack/react-query";
import { api, type ApplicantExtract } from "@/lib/api";
import { ErrorView } from "@/components/ErrorView";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";

interface Props {
  onAutofill: (fields: ApplicantExtract) => void;
}

/** File-upload widget that calls POST /api/applicant/extract and surfaces
 *  extracted fields to the parent form via onAutofill.
 *  Accepts text-based formats; PDF/docx are read as raw bytes — the backend
 *  LLM handles best-effort extraction for non-plain-text content. */
export function ResumeAutofill({ onAutofill }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);

  const extract = useMutation({
    mutationFn: (content: string) => api.extractApplicant(content),
    onSuccess: (data) => {
      // Drop empty-string and null/undefined values — only pre-fill fields the
      // LLM actually found so we don't overwrite existing entries with blanks.
      const filled = Object.fromEntries(
        Object.entries(data).filter(([, v]) => v != null && v !== ""),
      ) as ApplicantExtract;
      onAutofill(filled);
    },
  });

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = ev.target?.result;
      if (typeof text === "string") extract.mutate(text);
    };
    reader.readAsText(file);
    // Reset so re-uploading the same file fires onChange again.
    e.target.value = "";
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        {/* sr-only label satisfies htmlFor accessibility requirement;
            the Button triggers the hidden input programmatically. */}
        <Label htmlFor="resume-upload" className="sr-only">
          Upload résumé file (.txt, .md, .tex, .pdf, .docx)
        </Label>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={extract.isPending}
          onClick={() => inputRef.current?.click()}
        >
          {extract.isPending ? "Extracting…" : "Auto-fill from résumé"}
        </Button>
        <input
          ref={inputRef}
          id="resume-upload"
          type="file"
          accept=".txt,.md,.tex,.pdf,.docx"
          className="sr-only"
          onChange={handleChange}
        />
      </div>
      {extract.isSuccess && (
        <p className="text-xs text-muted-foreground">
          Fields auto-filled — review the values, then click Save.
        </p>
      )}
      {extract.isError && <ErrorView error={extract.error} />}
    </div>
  );
}
