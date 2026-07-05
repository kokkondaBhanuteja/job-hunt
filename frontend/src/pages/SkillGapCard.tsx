import { useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyView } from "@/components/EmptyView";
import { ErrorView } from "@/components/ErrorView";
import { LoadingView } from "@/components/LoadingView";
import { api } from "@/lib/api";
import { QUERY_KEYS } from "@/lib/constants";

export function SkillGapCard() {
  const q = useQuery({ queryKey: QUERY_KEYS.skillGap, queryFn: api.skillGap });

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Skill gaps</CardTitle>
      </CardHeader>
      <CardContent>
        {q.isError && <ErrorView error={q.error} />}
        {!q.isError && !q.data && <LoadingView />}
        {q.data && q.data.gaps.length === 0 && (
          <EmptyView icon={null}>No skill gaps found.</EmptyView>
        )}
        {q.data && q.data.gaps.length > 0 && (
          <>
            <div className="divide-y divide-border">
              {q.data.gaps.map(({ skill, count }) => (
                <div key={skill} className="flex justify-between gap-3 py-1.5 text-sm">
                  <span className="text-foreground">{skill}</span>
                  <Badge variant="secondary">{count}</Badge>
                </div>
              ))}
            </div>
            <div className="mt-3 text-[11px] text-muted-foreground">
              across {q.data.considered} scored jobs
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
