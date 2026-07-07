import { CheckCircle2, Circle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { HomeSetup } from "@/lib/api";
import { ROUTES } from "@/lib/constants";
import { Link } from "@/lib/router";

interface Props {
  setup: HomeSetup;
}

interface CheckItemProps {
  done: boolean;
  label: string;
  to: string;
}

function CheckItem({ done, label, to }: CheckItemProps) {
  return (
    <div className="flex items-center gap-3 py-2">
      {done ? (
        <CheckCircle2 className="h-4 w-4 shrink-0 text-primary" aria-hidden />
      ) : (
        <Circle className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
      )}
      <span className="text-sm">
        {done ? (
          label
        ) : (
          <Link to={to} className="text-foreground underline-offset-4 hover:underline">
            {label}
          </Link>
        )}
      </span>
    </div>
  );
}

export function SetupChecklist({ setup }: Props) {
  const watchlistDone = setup.watchlist_count > 0;
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Getting started</CardTitle>
      </CardHeader>
      <CardContent className="divide-y divide-border">
        <CheckItem done={setup.resume} label="Add a résumé" to={ROUTES.resumes} />
        <CheckItem done={setup.applicant} label="Complete your profile" to={ROUTES.settings} />
        <CheckItem done={setup.context} label="Add career context" to={ROUTES.settings} />
        <CheckItem done={setup.search_prefs} label="Set search preferences" to={ROUTES.settings} />
        <CheckItem done={setup.apply_policy} label="Set apply policy" to={ROUTES.settings} />
        {/* Watchlist shows a count — always link so users can add companies */}
        <div className="flex items-center gap-3 py-2">
          {watchlistDone ? (
            <CheckCircle2 className="h-4 w-4 shrink-0 text-primary" aria-hidden />
          ) : (
            <Circle className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
          )}
          <span className="text-sm">
            <Link to={ROUTES.settings} className="text-foreground underline-offset-4 hover:underline">
              Manage watchlist
            </Link>
            {watchlistDone && (
              <span className="ml-1 text-muted-foreground">
                ({setup.watchlist_count} companies)
              </span>
            )}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
