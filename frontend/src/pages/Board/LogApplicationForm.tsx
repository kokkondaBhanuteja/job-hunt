import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ErrorView } from "@/components/ErrorView";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { QUERY_KEYS } from "@/lib/constants";

export function LogApplicationForm({
  jobId,
  variantOptions,
}: {
  jobId: number;
  variantOptions: string[];
}) {
  const qc = useQueryClient();
  const [variant, setVariant] = useState("");
  const [cover, setCover] = useState("");
  const active = variant || variantOptions[0] || "";

  const apply = useMutation({
    mutationFn: () =>
      api.logApplication({ job_id: jobId, variant_slug: active, cover_letter: cover }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QUERY_KEYS.board });
      qc.invalidateQueries({ queryKey: QUERY_KEYS.job(jobId) });
    },
  });

  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <Label htmlFor="log-variant">Variant</Label>
        {variantOptions.length === 0 ? (
          <div className="rounded-md border border-dashed border-border px-3 py-2 text-xs text-muted-foreground">
            (no variant available)
          </div>
        ) : (
          <Select value={active} onValueChange={setVariant}>
            <SelectTrigger id="log-variant">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {variantOptions.map((v) => (
                <SelectItem key={v} value={v}>
                  {v}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="log-cover">Cover letter / notes</Label>
        <Textarea
          id="log-cover"
          placeholder="Cover letter / notes…"
          value={cover}
          onChange={(e) => setCover(e.target.value)}
          rows={4}
        />
      </div>
      <Button
        disabled={!active || apply.isPending}
        onClick={() => apply.mutate()}
        className="w-full sm:w-auto"
      >
        {apply.isPending ? "Saving…" : "Mark applied"}
      </Button>
      {apply.isError && <ErrorView error={apply.error} />}
      {apply.isSuccess && (
        <div className="text-sm text-emerald-600 dark:text-emerald-400">Logged ✓</div>
      )}
    </div>
  );
}
