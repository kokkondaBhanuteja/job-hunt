import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, getApiBase, getToken, setConfig } from "@/lib/api";
import { DEFAULT_API_BASE, QUERY_KEYS } from "@/lib/constants";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function ConnectionPanel() {
  const qc = useQueryClient();
  const [base, setBase] = useState(getApiBase());
  const [saved, setSaved] = useState(false);

  const health = useQuery({ queryKey: QUERY_KEYS.health, queryFn: api.health, retry: false });

  function save() {
    // Auth is injected by the nginx proxy (Docker stack); preserve any existing token untouched.
    setConfig(base.trim(), getToken());
    setSaved(true);
    qc.invalidateQueries();
    setTimeout(() => setSaved(false), 1500);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Connection</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="conn-base">API base</Label>
          <Input
            id="conn-base"
            value={base}
            onChange={(e) => setBase(e.target.value)}
            placeholder={DEFAULT_API_BASE}
          />
          <p className="text-xs text-muted-foreground">
            Auth is injected automatically by the proxy — no token to set here.
          </p>
        </div>

        <Button onClick={save}>{saved ? "Saved ✓" : "Save"}</Button>

        <div className="space-y-2 pt-2">
          {health.isSuccess ? (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <Badge className="bg-emerald-500/15 text-emerald-600 hover:bg-emerald-500/20 dark:text-emerald-400">
                  connected
                </Badge>
                <span className="font-mono text-xs text-muted-foreground">
                  datastore={health.data.datastore} · sources={health.data.sources.join(",")}
                </span>
              </div>
              <div className="space-y-0.5 font-mono text-[11px] text-muted-foreground">
                {Object.entries(health.data.llm).map(([task, cfg]) => (
                  <div key={task}>
                    {task}: {cfg.provider}/{cfg.model}
                  </div>
                ))}
              </div>
            </>
          ) : (
            <Badge variant="destructive">not connected</Badge>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
