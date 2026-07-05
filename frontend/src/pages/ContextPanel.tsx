import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ErrorView } from "@/components/ErrorView";
import { api } from "@/lib/api";
import { QUERY_KEYS } from "@/lib/constants";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

const FORMATS = ["md", "json"] as const;

/** Settings section: the user's career context, injected into every AI prompt. */
export function ContextPanel() {
  const qc = useQueryClient();
  const ctx = useQuery({
    queryKey: QUERY_KEYS.context,
    queryFn: api.getContext,
  });
  const [content, setContent] = useState("");
  const [format, setFormat] = useState<string>("md");
  const [dirty, setDirty] = useState(false);

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
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Career context</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-muted-foreground">
          Paste your résumé/context (Markdown or JSON). It is injected into every AI score,
          tailor, cover letter, and review — so the AI always knows you.
        </p>
        {ctx.isError && <ErrorView error={ctx.error} />}

        <div className="space-y-1.5">
          <Label htmlFor="ctx-format">Format</Label>
          <Select
            value={format}
            onValueChange={(v) => {
              setFormat(v);
              setDirty(true);
            }}
          >
            <SelectTrigger id="ctx-format" className="w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {FORMATS.map((f) => (
                <SelectItem key={f} value={f}>
                  {f}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="ctx-content" className="sr-only">
            Career context
          </Label>
          <Textarea
            id="ctx-content"
            rows={12}
            className="font-mono text-xs"
            placeholder={"# About me\n\nBackend engineer, 2y Node/NestJS + Postgres…"}
            value={content}
            onChange={(e) => {
              setContent(e.target.value);
              setDirty(true);
            }}
          />
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Button disabled={!content.trim() || save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? "Saving…" : !dirty && save.isSuccess ? "Saved ✓" : "Save context"}
          </Button>
          {ctx.data?.updated_at && (
            <span className="font-mono text-xs text-muted-foreground">
              last updated {ctx.data.updated_at}
            </span>
          )}
        </div>

        {save.isError && <ErrorView error={save.error} />}
      </CardContent>
    </Card>
  );
}
