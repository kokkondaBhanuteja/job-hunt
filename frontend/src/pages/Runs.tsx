import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play, Search } from "lucide-react";
import { ErrorView } from "@/components/ErrorView";
import { LoadingView } from "@/components/LoadingView";
import { Pagination, paginate } from "@/components/Pagination";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api, type Run } from "@/lib/api";
import { QUERY_KEYS, RUNS_POLL_MS } from "@/lib/constants";

const PAGE_SIZE = 10;

function statusBadge(status: string) {
  switch (status) {
    case "done":
      return <Badge className="bg-emerald-500/15 text-emerald-600 hover:bg-emerald-500/20 dark:text-emerald-400">done</Badge>;
    case "running":
      return <Badge className="bg-primary/15 text-primary hover:bg-primary/20">running</Badge>;
    case "failed":
      return <Badge variant="destructive">failed</Badge>;
    case "cancelled":
      return <Badge className="bg-amber-500/15 text-amber-600 hover:bg-amber-500/20 dark:text-amber-400">cancelled</Badge>;
    default:
      return <Badge variant="secondary">{status}</Badge>;
  }
}

function lastLogLine(log: string | null | undefined) {
  return log?.trim().split("\n").slice(-1)[0] ?? "";
}

export function Runs() {
  const qc = useQueryClient();
  const runs = useQuery({ queryKey: QUERY_KEYS.runs, queryFn: api.runs, refetchInterval: RUNS_POLL_MS });
  const [page, setPage] = useState(1);

  const discover = useMutation({
    mutationFn: api.discover,
    onSuccess: () => qc.invalidateQueries({ queryKey: QUERY_KEYS.runs }),
  });
  const score = useMutation({
    mutationFn: api.score,
    onSuccess: () => qc.invalidateQueries({ queryKey: QUERY_KEYS.runs }),
  });

  const all = runs.data ?? [];
  const pageItems = paginate(all, page, PAGE_SIZE);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold tracking-tight">Runs</h1>
        <div className="ml-auto flex flex-wrap gap-2">
          <Button disabled={discover.isPending} onClick={() => discover.mutate()}>
            <Search className="h-4 w-4" />
            {discover.isPending ? "Starting…" : "Discover now"}
          </Button>
          <Button variant="outline" disabled={score.isPending} onClick={() => score.mutate()}>
            <Play className="h-4 w-4" />
            {score.isPending ? "Starting…" : "Score pending"}
          </Button>
        </div>
      </div>

      {(discover.isError || score.isError) && (
        <ErrorView error={discover.error || score.error} />
      )}

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Recent pipeline runs</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 p-4 md:p-0">
          {runs.isError ? (
            <div className="p-2">
              <ErrorView error={runs.error} title="Couldn’t load runs" />
            </div>
          ) : !runs.data ? (
            <div className="p-2">
              <LoadingView label="Loading runs…" rows={3} />
            </div>
          ) : all.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              No runs yet — hit <span className="font-medium text-foreground">Discover now</span>.
            </div>
          ) : (
            <>
              <div className="hidden md:block md:overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-16">#</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">Found</TableHead>
                      <TableHead className="text-right">New</TableHead>
                      <TableHead>Started</TableHead>
                      <TableHead className="max-w-[320px]">Log</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {pageItems.map((r) => (
                      <TableRow key={r.id}>
                        <TableCell className="font-mono text-xs">{r.id}</TableCell>
                        <TableCell>{statusBadge(r.status)}</TableCell>
                        <TableCell className="text-right tabular-nums">{r.jobs_found}</TableCell>
                        <TableCell className="text-right tabular-nums">{r.jobs_new}</TableCell>
                        <TableCell className="font-mono text-xs text-muted-foreground">
                          {(r.started_at ?? "").slice(0, 19)}
                        </TableCell>
                        <TableCell className="max-w-[320px] truncate font-mono text-xs text-muted-foreground">
                          {lastLogLine(r.log)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>

              <div className="flex flex-col gap-2 md:hidden">
                {pageItems.map((r) => (
                  <RunCard key={r.id} run={r} />
                ))}
              </div>

              <div className="px-0 pb-1 pt-2 md:px-4 md:pb-3">
                <Pagination
                  page={page}
                  pageSize={PAGE_SIZE}
                  total={all.length}
                  onPageChange={setPage}
                  itemName="runs"
                />
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function RunCard({ run }: { run: Run }) {
  return (
    <div className="rounded-lg border border-border bg-card p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs text-muted-foreground">#{run.id}</span>
          {statusBadge(run.status)}
        </div>
        <span className="font-mono text-[11px] text-muted-foreground">
          {(run.started_at ?? "").slice(0, 19)}
        </span>
      </div>
      <div className="mt-2 flex gap-4 text-xs">
        <div>
          <span className="text-muted-foreground">Found</span>{" "}
          <span className="font-semibold tabular-nums">{run.jobs_found}</span>
        </div>
        <div>
          <span className="text-muted-foreground">New</span>{" "}
          <span className="font-semibold tabular-nums">{run.jobs_new}</span>
        </div>
      </div>
      {lastLogLine(run.log) && (
        <div className="mt-2 truncate font-mono text-[11px] text-muted-foreground">
          {lastLogLine(run.log)}
        </div>
      )}
    </div>
  );
}
