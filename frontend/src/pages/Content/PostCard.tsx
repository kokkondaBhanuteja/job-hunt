import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, ExternalLink, X } from "lucide-react";
import { ErrorView } from "@/components/ErrorView";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { api, type Post } from "@/lib/api";
import { QUERY_KEYS } from "@/lib/constants";

interface Props {
  post: Post;
}

/** Single social-post draft card with copy / mark-posted / dismiss actions. */
export function PostCard({ post }: Props) {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: QUERY_KEYS.posts });

  const markPosted = useMutation({
    mutationFn: () => api.setPostStatus(post.id, "posted"),
    onSuccess: invalidate,
  });
  const dismiss = useMutation({
    mutationFn: () => api.setPostStatus(post.id, "dismissed"),
    onSuccess: invalidate,
  });

  const busy = markPosted.isPending || dismiss.isPending;

  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="whitespace-pre-wrap rounded-md border border-border bg-secondary/40 px-3 py-2.5 text-[13px] leading-relaxed">
          {post.body}
        </div>

        {(post.topic || post.source_url) && (
          <div className="flex flex-wrap items-center gap-2">
            {post.topic && (
              <Badge variant="secondary" className="font-normal">
                {post.topic}
              </Badge>
            )}
            {post.source_url && (
              <a
                href={post.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 rounded-md border border-border bg-background px-2 py-0.5 text-xs text-primary transition-colors hover:bg-secondary"
              >
                Source <ExternalLink className="h-3 w-3" />
              </a>
            )}
          </div>
        )}

        <div className="flex flex-wrap gap-1.5">
          <Button
            size="sm"
            variant="outline"
            onClick={() => void navigator.clipboard.writeText(post.body)}
          >
            <Copy className="h-3.5 w-3.5" />
            Copy
          </Button>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => markPosted.mutate()}>
            <Check className="h-3.5 w-3.5" />
            {markPosted.isPending ? "Marking…" : "Mark posted"}
          </Button>
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => dismiss.mutate()}>
            <X className="h-3.5 w-3.5" />
            {dismiss.isPending ? "Dismissing…" : "Dismiss"}
          </Button>
        </div>

        {markPosted.isError && <ErrorView error={markPosted.error} />}
        {dismiss.isError && <ErrorView error={dismiss.error} />}
      </CardContent>
    </Card>
  );
}
