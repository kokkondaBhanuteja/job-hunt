import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { EmptyView } from "@/components/EmptyView";
import { ErrorView } from "@/components/ErrorView";
import { LoadingView } from "@/components/LoadingView";
import { Pagination, paginate } from "@/components/Pagination";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api } from "@/lib/api";
import { EMAIL_CATEGORY, QUERY_KEYS } from "@/lib/constants";
import { EmailRow } from "./EmailRow";
import { EmailDetail } from "./EmailDetail";

const CATEGORY_ALL = "__all__";
const CATEGORY_OPTIONS = [CATEGORY_ALL, ...Object.values(EMAIL_CATEGORY)];
const PAGE_SIZE = 20;

function labelFor(v: string) {
  return v === CATEGORY_ALL ? "All categories" : v.replace(/_/g, " ");
}

/** Read-only triaged inbox: filterable email list + detail panel + non-blocking sync. */
export function Inbox() {
  const qc = useQueryClient();
  const [category, setCategory] = useState<string>(CATEGORY_ALL);
  const [selected, setSelected] = useState<number | null>(null);
  const [page, setPage] = useState(1);
  const activeCategory = category === CATEGORY_ALL ? "" : category;
  useEffect(() => {
    setPage(1);
  }, [activeCategory]);

  const emails = useQuery({
    queryKey: [...QUERY_KEYS.emails, activeCategory],
    queryFn: () => api.emails(activeCategory ? { category: activeCategory } : {}),
  });
  const sync = useMutation({
    mutationFn: api.syncEmails,
    onSuccess: () => qc.invalidateQueries({ queryKey: QUERY_KEYS.emails }),
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <h1 className="text-xl font-semibold tracking-tight">Inbox</h1>
        <div className="ml-auto flex flex-wrap items-end gap-2">
          <div className="space-y-1.5">
            <Label htmlFor="inbox-category" className="text-xs text-muted-foreground">
              Filter
            </Label>
            <Select value={category} onValueChange={setCategory}>
              <SelectTrigger id="inbox-category" className="w-[180px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {CATEGORY_OPTIONS.map((c) => (
                  <SelectItem key={c} value={c}>
                    {labelFor(c)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button disabled={sync.isPending} onClick={() => sync.mutate()}>
            <RefreshCw className={"h-4 w-4 " + (sync.isPending ? "animate-spin" : "")} />
            {sync.isPending ? "Syncing…" : "Sync inbox"}
          </Button>
        </div>
      </div>

      {sync.isError && <ErrorView error={sync.error} />}

      <div className="flex gap-3">
        <div className="flex-1 space-y-2 min-w-0">
          {emails.isError ? (
            <ErrorView error={emails.error} />
          ) : !emails.data ? (
            <LoadingView label="Loading inbox…" rows={5} />
          ) : emails.data.length === 0 ? (
            <EmptyView>No emails yet — hit &ldquo;Sync inbox&rdquo;.</EmptyView>
          ) : (
            <>
              {paginate(emails.data, page, PAGE_SIZE).map((e) => (
                <EmailRow
                  key={e.id}
                  email={e}
                  active={e.id === selected}
                  onSelect={() => setSelected(e.id)}
                />
              ))}
              <Pagination
                page={page}
                pageSize={PAGE_SIZE}
                total={emails.data.length}
                onPageChange={setPage}
                itemName="emails"
              />
            </>
          )}
        </div>
        {selected != null && <EmailDetail id={selected} onClose={() => setSelected(null)} />}
      </div>
    </div>
  );
}
