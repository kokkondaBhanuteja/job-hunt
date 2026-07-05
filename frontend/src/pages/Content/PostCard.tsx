import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type Post } from "../../lib/api";
import { QUERY_KEYS } from "../../lib/constants";

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
    <div className="post-card">
      <div className="post-body">{post.body}</div>
      <div className="post-meta">
        {post.topic && <span className="post-topic">{post.topic}</span>}
        {post.source_url && (
          <a
            className="chip link"
            href={post.source_url}
            target="_blank"
            rel="noopener noreferrer"
          >
            Source
          </a>
        )}
      </div>
      <div className="btn-row">
        <button onClick={() => void navigator.clipboard.writeText(post.body)}>Copy</button>
        <button disabled={busy} onClick={() => markPosted.mutate()}>
          {markPosted.isPending ? "Marking…" : "Mark posted"}
        </button>
        <button disabled={busy} onClick={() => dismiss.mutate()}>
          {dismiss.isPending ? "Dismissing…" : "Dismiss"}
        </button>
      </div>
      {markPosted.isError && (
        <div className="banner error">{String(markPosted.error)}</div>
      )}
      {dismiss.isError && (
        <div className="banner error">{String(dismiss.error)}</div>
      )}
    </div>
  );
}
