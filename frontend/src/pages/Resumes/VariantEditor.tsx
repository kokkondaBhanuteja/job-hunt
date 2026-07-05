import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Save } from "lucide-react";
import { ErrorView } from "@/components/ErrorView";
import { LoadingView } from "@/components/LoadingView";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { QUERY_KEYS } from "@/lib/constants";
import { SkillGapCard } from "@/pages/SkillGapCard";

interface Props {
  /** null = new-variant mode; string = existing slug */
  slug: string | null;
  onSaved: (slug: string) => void;
}

export function VariantEditor({ slug, onSaved }: Props) {
  const qc = useQueryClient();
  const isNew = slug === null;

  // Stable key for the disabled query when creating a new variant
  const slugForQuery = slug ?? "";
  const detail = useQuery({
    queryKey: QUERY_KEYS.variant(slugForQuery),
    queryFn: () => api.variant(slugForQuery),
    enabled: !isNew,
  });

  const [formSlug, setFormSlug] = useState(slug ?? "");
  const [company, setCompany] = useState("");
  const [body, setBody] = useState("");
  const [tagsRaw, setTagsRaw] = useState("");

  // Populate form fields once the fetch resolves
  useEffect(() => {
    if (detail.data) {
      setCompany(detail.data.company ?? "");
      setBody(detail.data.body ?? "");
      setTagsRaw(detail.data.tags.join(", "));
    }
  }, [detail.data]);

  const save = useMutation({
    mutationFn: () =>
      api.saveVariant({
        slug: formSlug.trim(),
        company: company.trim() || undefined,
        body,
        tags: tagsRaw.split(",").map((t) => t.trim()).filter(Boolean),
      }),
    onSuccess: (result) => {
      void qc.invalidateQueries({ queryKey: QUERY_KEYS.variants });
      // Invalidate the variant detail cache for the saved slug
      void qc.invalidateQueries({ queryKey: QUERY_KEYS.variant(result.slug) });
      onSaved(result.slug);
    },
  });

  if (!isNew && detail.isLoading) return <LoadingView label="Loading variant…" />;
  if (!isNew && detail.isError) return <ErrorView error={detail.error} />;

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">
            {isNew ? "New résumé variant" : slug}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {isNew && (
            <div className="space-y-1">
              <Label htmlFor="res-slug">Slug</Label>
              <Input
                id="res-slug"
                value={formSlug}
                onChange={(e) => setFormSlug(e.target.value)}
                placeholder="e.g. base, google-swe"
              />
            </div>
          )}
          <div className="space-y-1">
            <Label htmlFor="res-company">Company (optional)</Label>
            <Input
              id="res-company"
              value={company}
              onChange={(e) => setCompany(e.target.value)}
              placeholder="e.g. Acme Corp"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="res-tags">Tags (comma-separated)</Label>
            <Input
              id="res-tags"
              value={tagsRaw}
              onChange={(e) => setTagsRaw(e.target.value)}
              placeholder="e.g. backend, python"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="res-body">Body (LaTeX / Markdown)</Label>
            <Textarea
              id="res-body"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              className="min-h-[300px] font-mono text-xs"
              placeholder="Paste your résumé source here…"
            />
          </div>
          {save.isError && <ErrorView error={save.error} />}
          <Button
            disabled={save.isPending || !formSlug.trim()}
            onClick={() => save.mutate()}
          >
            <Save className="h-4 w-4" />
            {save.isPending ? "Saving…" : "Save"}
          </Button>
        </CardContent>
      </Card>
      <SkillGapCard />
    </div>
  );
}
