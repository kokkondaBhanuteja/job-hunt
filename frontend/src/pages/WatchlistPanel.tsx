import { useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { EmptyView } from "@/components/EmptyView";
import { ErrorView } from "@/components/ErrorView";
import { LoadingView } from "@/components/LoadingView";
import { api, type WatchEntry } from "@/lib/api";
import { ATS_OPTIONS, QUERY_KEYS } from "@/lib/constants";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export function WatchlistPanel() {
  const qc = useQueryClient();
  const watchlist = useQuery({ queryKey: QUERY_KEYS.watchlist, queryFn: api.watchlist });
  const [company, setCompany] = useState("");
  const [ats, setAts] = useState<string>(ATS_OPTIONS[0]);
  const [boardToken, setBoardToken] = useState("");

  const addWatch = useMutation({
    mutationFn: () => api.addWatch({ company, ats, board_token: boardToken }),
    onSuccess: () => {
      setCompany(""); setAts(ATS_OPTIONS[0]); setBoardToken("");
      qc.invalidateQueries({ queryKey: QUERY_KEYS.watchlist });
    },
  });
  const removeWatch = useMutation({
    mutationFn: (id: number) => api.removeWatch(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: QUERY_KEYS.watchlist }),
  });
  const setEnabled = useMutation({
    mutationFn: (v: { id: number; enabled: boolean }) => api.setWatchEnabled(v.id, v.enabled),
    onSuccess: () => qc.invalidateQueries({ queryKey: QUERY_KEYS.watchlist }),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Watchlist</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-[1fr_auto_1fr_auto] sm:items-end">
          <Field label="Company" id="wl-company">
            <Input id="wl-company" value={company} onChange={(e) => setCompany(e.target.value)} placeholder="Acme Corp" />
          </Field>
          <Field label="ATS" id="wl-ats">
            <Select value={ats} onValueChange={setAts}>
              <SelectTrigger id="wl-ats" className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                {ATS_OPTIONS.map((a) => <SelectItem key={a} value={a}>{a}</SelectItem>)}
              </SelectContent>
            </Select>
          </Field>
          <Field label="Board token" id="wl-token">
            <Input id="wl-token" value={boardToken} onChange={(e) => setBoardToken(e.target.value)} placeholder="token" />
          </Field>
          <Button disabled={!company || !boardToken || addWatch.isPending} onClick={() => addWatch.mutate()}>
            Add
          </Button>
        </div>
        {addWatch.isError && <ErrorView error={addWatch.error} />}

        {watchlist.isError ? (
          <ErrorView error={watchlist.error} title="Couldn't load watchlist" />
        ) : !watchlist.data ? (
          <LoadingView label="Loading watchlist…" rows={3} />
        ) : watchlist.data.length === 0 ? (
          <EmptyView>No companies in the watchlist yet.</EmptyView>
        ) : (
          <div className="overflow-x-auto rounded-md border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Company</TableHead>
                  <TableHead>ATS</TableHead>
                  <TableHead>Token</TableHead>
                  <TableHead className="text-right">Enabled</TableHead>
                  <TableHead className="sr-only">Remove</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {watchlist.data.map((e) => (
                  <WatchRow key={e.id} entry={e}
                    onToggle={(enabled) => setEnabled.mutate({ id: e.id, enabled })}
                    onRemove={() => removeWatch.mutate(e.id)}
                  />
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function WatchRow({ entry, onToggle, onRemove }: {
  entry: WatchEntry;
  onToggle: (enabled: boolean) => void;
  onRemove: () => void;
}) {
  return (
    <TableRow>
      <TableCell className="font-medium">{entry.company}</TableCell>
      <TableCell><Badge variant="secondary">{entry.ats}</Badge></TableCell>
      <TableCell className="max-w-[10rem] truncate font-mono text-xs text-muted-foreground">{entry.board_token}</TableCell>
      <TableCell className="text-right">
        <Switch checked={entry.enabled} onCheckedChange={onToggle} aria-label={`Enable ${entry.company}`} />
      </TableCell>
      <TableCell className="text-right">
        <Button variant="ghost" size="icon" onClick={onRemove} aria-label={`Remove ${entry.company}`}>
          <Trash2 className="h-4 w-4" />
        </Button>
      </TableCell>
    </TableRow>
  );
}

function Field({ label, id, children }: { label: string; id: string; children: ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id} className="text-xs text-muted-foreground">{label}</Label>
      {children}
    </div>
  );
}
