import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ErrorView } from "@/components/ErrorView";
import { api, type Applicant, type ApplicantExtract } from "@/lib/api";
import { QUERY_KEYS } from "@/lib/constants";
import { ResumeAutofill } from "./ResumeAutofill";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type StringField =
  | "first_name" | "last_name" | "email" | "phone" | "location"
  | "linkedin_url" | "github_url" | "portfolio_url" | "work_authorization"
  | "notice_period" | "expected_ctc" | "current_ctc" | "years_experience"
  | "referral_source";

const FIELDS: { key: StringField; label: string }[] = [
  { key: "first_name", label: "First name" },
  { key: "last_name", label: "Last name" },
  { key: "email", label: "Email" },
  { key: "phone", label: "Phone" },
  { key: "location", label: "Location" },
  { key: "linkedin_url", label: "LinkedIn URL" },
  { key: "github_url", label: "GitHub URL" },
  { key: "portfolio_url", label: "Portfolio URL" },
  { key: "work_authorization", label: "Work authorization" },
  { key: "notice_period", label: "Notice period" },
  { key: "expected_ctc", label: "Expected CTC" },
  { key: "current_ctc", label: "Current CTC" },
  { key: "years_experience", label: "Years of experience" },
  { key: "referral_source", label: "Referral source" },
];

/** Settings section: the applicant's personal details for ATS auto-fill. */
export function ApplicantPanel() {
  const qc = useQueryClient();
  const result = useQuery({
    queryKey: QUERY_KEYS.applicant,
    queryFn: api.getApplicant,
  });
  const [form, setForm] = useState<Partial<Applicant>>({});
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (result.data && !dirty) setForm(result.data);
  }, [result.data, dirty]);

  const save = useMutation({
    mutationFn: () => api.setApplicant(form),
    onSuccess: () => {
      setDirty(false);
      qc.invalidateQueries({ queryKey: QUERY_KEYS.applicant });
    },
  });

  function handleChange(key: StringField, val: string) {
    setForm((f) => ({ ...f, [key]: val }));
    setDirty(true);
  }

  function handleAutofill(fields: ApplicantExtract) {
    // Merge extracted fields over current form — user reviews before saving.
    setForm((f) => ({ ...f, ...fields }));
    setDirty(true);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Applicant profile</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-xs text-muted-foreground">
          Personal details used by Auto-fill to populate ATS forms. Sponsorship and
          relocation toggles are coming in v2.
        </p>
        <ResumeAutofill onAutofill={handleAutofill} />
        {result.isError && <ErrorView error={result.error} />}
        <div className="grid gap-4 md:grid-cols-2">
          {FIELDS.map(({ key, label }) => (
            <div className="space-y-1.5" key={key}>
              <Label htmlFor={key}>{label}</Label>
              <Input
                id={key}
                value={form[key] ?? ""}
                onChange={(e) => handleChange(key, e.target.value)}
              />
            </div>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button disabled={save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? "Saving…" : !dirty && save.isSuccess ? "Saved ✓" : "Save profile"}
          </Button>
          {result.data?.updated_at && (
            <span className="font-mono text-xs text-muted-foreground">
              last updated {result.data.updated_at}
            </span>
          )}
        </div>
        {save.isError && <ErrorView error={save.error} />}
      </CardContent>
    </Card>
  );
}
