import { useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ErrorView } from "@/components/ErrorView";
import { LoadingView } from "@/components/LoadingView";
import { Pagination, paginate } from "@/components/Pagination";
import { api, type Profile } from "@/lib/api";
import { QUERY_KEYS } from "@/lib/constants";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const PAGE_SIZE = 10;

export function ProfilesPanel() {
  const qc = useQueryClient();
  const profiles = useQuery({
    queryKey: QUERY_KEYS.profiles,
    queryFn: api.profiles,
  });

  const [pName, setPName] = useState("");
  const [pKeywords, setPKeywords] = useState("");
  const [pLocation, setPLocation] = useState("");
  const [pPages, setPPages] = useState(1);
  const [page, setPage] = useState(1);

  const addProfile = useMutation({
    mutationFn: () =>
      api.addProfile({ name: pName, keywords: pKeywords, location: pLocation, pages: pPages }),
    onSuccess: () => {
      setPName("");
      setPKeywords("");
      setPLocation("");
      qc.invalidateQueries({ queryKey: QUERY_KEYS.profiles });
    },
  });
  const toggle = useMutation({
    mutationFn: (v: { id: number; enabled: boolean }) => api.setProfileEnabled(v.id, v.enabled),
    onSuccess: () => qc.invalidateQueries({ queryKey: QUERY_KEYS.profiles }),
  });

  const all = profiles.data ?? [];
  const pageItems = paginate(all, page, PAGE_SIZE);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Search profiles</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 md:grid-cols-[1fr_1.5fr_1fr_5rem_auto] md:items-end">
          <Field label="Name" id="pf-name">
            <Input id="pf-name" value={pName} onChange={(e) => setPName(e.target.value)} />
          </Field>
          <Field label="Keywords" id="pf-keywords">
            <Input
              id="pf-keywords"
              placeholder="e.g. nestjs backend"
              value={pKeywords}
              onChange={(e) => setPKeywords(e.target.value)}
            />
          </Field>
          <Field label="Location" id="pf-location">
            <Input id="pf-location" value={pLocation} onChange={(e) => setPLocation(e.target.value)} />
          </Field>
          <Field label="Pages" id="pf-pages">
            <Input
              id="pf-pages"
              type="number"
              min={1}
              value={pPages}
              onChange={(e) => setPPages(Number(e.target.value))}
            />
          </Field>
          <Button
            disabled={!pName || !pKeywords || !pLocation || addProfile.isPending}
            onClick={() => addProfile.mutate()}
          >
            Add
          </Button>
        </div>
        {addProfile.isError && <ErrorView error={addProfile.error} />}

        {profiles.isError ? (
          <ErrorView error={profiles.error} title="Couldn’t load profiles" />
        ) : !profiles.data ? (
          <LoadingView label="Loading profiles…" rows={3} />
        ) : all.length === 0 ? (
          <div className="rounded-md border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
            No profiles yet.
          </div>
        ) : (
          <>
            <div className="hidden overflow-x-auto rounded-md border border-border md:block">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-12">#</TableHead>
                    <TableHead>Name</TableHead>
                    <TableHead>Keywords</TableHead>
                    <TableHead>Location</TableHead>
                    <TableHead className="text-right">Pages</TableHead>
                    <TableHead className="text-right">Enabled</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {pageItems.map((p) => (
                    <TableRow key={p.id}>
                      <TableCell className="font-mono text-xs text-muted-foreground">{p.id}</TableCell>
                      <TableCell>{p.name}</TableCell>
                      <TableCell className="text-muted-foreground">{p.keywords}</TableCell>
                      <TableCell className="text-muted-foreground">{p.location}</TableCell>
                      <TableCell className="text-right tabular-nums">{p.pages}</TableCell>
                      <TableCell className="text-right">
                        <Switch
                          checked={!!p.enabled}
                          onCheckedChange={(v) => toggle.mutate({ id: p.id, enabled: v })}
                          aria-label={`Enable profile ${p.name}`}
                        />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>

            <div className="flex flex-col gap-2 md:hidden">
              {pageItems.map((p) => (
                <ProfileCard
                  key={p.id}
                  profile={p}
                  onToggle={(enabled) => toggle.mutate({ id: p.id, enabled })}
                />
              ))}
            </div>

            <Pagination
              page={page}
              pageSize={PAGE_SIZE}
              total={all.length}
              onPageChange={setPage}
              itemName="profiles"
            />
          </>
        )}
      </CardContent>
    </Card>
  );
}

function ProfileCard({
  profile,
  onToggle,
}: {
  profile: Profile;
  onToggle: (enabled: boolean) => void;
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <div className="flex items-center gap-2">
            <span className="font-mono text-[11px] text-muted-foreground">#{profile.id}</span>
            <span className="truncate text-sm font-semibold">{profile.name}</span>
          </div>
          <div className="text-xs text-muted-foreground">
            <span className="text-foreground">{profile.keywords}</span>
            {profile.location ? ` · ${profile.location}` : ""}
            {" · "}
            <span className="tabular-nums">{profile.pages} page{profile.pages === 1 ? "" : "s"}</span>
          </div>
        </div>
        <Switch
          checked={!!profile.enabled}
          onCheckedChange={onToggle}
          aria-label={`Enable profile ${profile.name}`}
        />
      </div>
    </div>
  );
}

function Field({ label, id, children }: { label: string; id: string; children: ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id} className="text-xs text-muted-foreground">
        {label}
      </Label>
      {children}
    </div>
  );
}
