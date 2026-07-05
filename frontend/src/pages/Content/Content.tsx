import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PenLine, Sparkles } from "lucide-react";
import { EmptyView } from "@/components/EmptyView";
import { ErrorView } from "@/components/ErrorView";
import { LoadingView } from "@/components/LoadingView";
import { Pagination, paginate } from "@/components/Pagination";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { QUERY_KEYS } from "@/lib/constants";
import { PostCard } from "./PostCard";

const PAGE_SIZE = 10;

/** Lists AI-drafted social posts for the user to review, copy, and act on. */
export function Content() {
  const qc = useQueryClient();
  const [page, setPage] = useState(1);

  const posts = useQuery({
    queryKey: QUERY_KEYS.posts,
    queryFn: api.posts,
  });

  const generate = useMutation({
    mutationFn: () => api.generatePost(),
    onSuccess: () => qc.invalidateQueries({ queryKey: QUERY_KEYS.posts }),
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold tracking-tight">Content</h1>
        <div className="ml-auto flex flex-wrap gap-2">
          <Button disabled={generate.isPending} onClick={() => generate.mutate()}>
            <Sparkles className="h-4 w-4" />
            {generate.isPending ? "Generating…" : "Generate draft now"}
          </Button>
        </div>
      </div>

      {generate.isError && <ErrorView error={generate.error} />}

      {posts.isError ? (
        <ErrorView error={posts.error} />
      ) : !posts.data ? (
        <LoadingView label="Loading posts…" rows={4} />
      ) : posts.data.length === 0 ? (
        <EmptyView icon={<PenLine className="h-6 w-6 opacity-60" aria-hidden />}>
          No drafts yet — hit &ldquo;Generate draft now&rdquo;.
        </EmptyView>
      ) : (
        <div className="space-y-3">
          {paginate(posts.data, page, PAGE_SIZE).map((p) => (
            <PostCard key={p.id} post={p} />
          ))}
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={posts.data.length}
            onPageChange={setPage}
            itemName="posts"
          />
        </div>
      )}
    </div>
  );
}
