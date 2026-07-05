import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { EmptyView } from "../../components/EmptyView";
import { ErrorView } from "../../components/ErrorView";
import { LoadingView } from "../../components/LoadingView";
import { api } from "../../lib/api";
import { QUERY_KEYS } from "../../lib/constants";
import { PostCard } from "./PostCard";

/** Lists AI-drafted social posts for the user to review, copy, and act on. */
export function Content() {
  const qc = useQueryClient();

  const posts = useQuery({
    queryKey: QUERY_KEYS.posts,
    queryFn: api.posts,
  });

  const generate = useMutation({
    mutationFn: () => api.generatePost(),
    onSuccess: () => qc.invalidateQueries({ queryKey: QUERY_KEYS.posts }),
  });

  return (
    <div className="page">
      <div className="page-head">
        <h1>Content</h1>
        <div className="actions">
          <button
            className="primary"
            disabled={generate.isPending}
            onClick={() => generate.mutate()}
          >
            {generate.isPending ? "Generating…" : "Generate draft now"}
          </button>
        </div>
      </div>
      {generate.isError && <ErrorView error={generate.error} />}
      {posts.isError ? (
        <ErrorView error={posts.error} />
      ) : !posts.data ? (
        <LoadingView label="Loading posts…" />
      ) : posts.data.length === 0 ? (
        <EmptyView>No drafts yet — hit "Generate draft now".</EmptyView>
      ) : (
        <div className="post-list">
          {posts.data.map((p) => (
            <PostCard key={p.id} post={p} />
          ))}
        </div>
      )}
    </div>
  );
}
