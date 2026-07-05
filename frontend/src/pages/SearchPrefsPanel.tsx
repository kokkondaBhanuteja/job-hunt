import { useEffect, useState, type ChangeEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ErrorView } from "@/components/ErrorView";
import { LoadingView } from "@/components/LoadingView";
import { api } from "@/lib/api";
import { QUERY_KEYS } from "@/lib/constants";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApplyPolicyView } from "./ApplyPolicyView";

/** Settings section: paste/upload Markdown search preferences → parsed into search profiles + apply policy. */
export function SearchPrefsPanel() {
  const qc = useQueryClient();
  const prefs = useQuery({
    queryKey: QUERY_KEYS.searchPrefs,
    queryFn: api.getSearchPrefs,
  });
  const policy = useQuery({
    queryKey: QUERY_KEYS.applyPolicy,
    queryFn: api.applyPolicy,
  });
  const [content, setContent] = useState("");
  const [dirty, setDirty] = useState(false);
  const [profilesCreated, setProfilesCreated] = useState<number | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);

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

  function handleFileChange(ev: ChangeEvent<HTMLInputElement>) {
    const input = ev.target;
    const file = input.files?.[0];
    // Reset the input value so re-selecting the same file re-fires change.
    input.value = "";
    if (!file) return;
    setFileError(null);
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target?.result;
      if (typeof text === "string") {
        setContent(text);
        setDirty(true);
        setProfilesCreated(null);
      } else {
        setFileError(`Couldn’t read ${file.name} — the file didn’t decode as text.`);
      }
    };
    reader.onerror = () =>
      setFileError(`Couldn’t read ${file.name}. Check the file still exists and is readable.`);
    reader.onabort = () => setFileError(`Reading ${file.name} was cancelled.`);
    reader.readAsText(file);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Search preferences</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-muted-foreground">
          Describe what roles/skills and locations to search for — I&apos;ll turn it into search
          profiles below.
        </p>
        {prefs.isError && <ErrorView error={prefs.error} />}

        <div className="space-y-1.5">
          <Label htmlFor="search-prefs-file">Upload .md or .txt</Label>
          <Input
            id="search-prefs-file"
            type="file"
            accept=".md,.txt"
            onChange={handleFileChange}
          />
          {fileError && (
            <p role="alert" className="text-xs text-destructive">
              {fileError}
            </p>
          )}
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="search-prefs-input" className="sr-only">
            Search preferences
          </Label>
          <Textarea
            id="search-prefs-input"
            rows={10}
            className="font-mono text-xs"
            placeholder={"# What I'm looking for\n\nBackend engineer roles (Node/NestJS, Python) in Berlin or remote…"}
            value={content}
            onChange={(e) => {
              setContent(e.target.value);
              setDirty(true);
              setProfilesCreated(null);
            }}
          />
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Button disabled={!content.trim() || save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? "Parsing…" : !dirty && save.isSuccess ? "Saved ✓" : "Parse & save"}
          </Button>
          {profilesCreated !== null && !save.isError && (
            <span className="font-mono text-xs text-muted-foreground">
              created {profilesCreated} profile{profilesCreated !== 1 ? "s" : ""}
            </span>
          )}
          {prefs.data?.updated_at && (
            <span className="font-mono text-xs text-muted-foreground">
              last updated {prefs.data.updated_at}
            </span>
          )}
        </div>

        {save.isError && <ErrorView error={save.error} />}

        <div className="space-y-2 pt-3 border-t border-border/60">
          <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Apply policy
          </h3>
          {policy.isLoading && <LoadingView rows={2} />}
          {policy.isError && <ErrorView error={policy.error} />}
          {policy.data && <ApplyPolicyView policy={policy.data} />}
        </div>
      </CardContent>
    </Card>
  );
}
