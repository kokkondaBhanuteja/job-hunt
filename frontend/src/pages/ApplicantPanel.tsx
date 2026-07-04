import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ErrorView } from "../components/ErrorView";
import { api, getToken, type Applicant } from "../lib/api";
import { QUERY_KEYS } from "../lib/constants";

// String-only fields rendered in v1. Boolean fields (needs_sponsorship,
// willing_to_relocate) are deferred to keep this file ≤150 lines.
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
    enabled: !!getToken(),
  });
  const [form, setForm] = useState<Partial<Applicant>>({});
  const [dirty, setDirty] = useState(false);

  // Pre-fill from stored applicant data once, until the user edits.
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

  return (
    <section className="card-block">
      <h2>Applicant profile</h2>
      <p className="muted small">
        Personal details used by Auto-fill to populate ATS forms. Sponsorship and
        relocation toggles are coming in v2.
      </p>
      {result.isError && <ErrorView error={result.error} />}
      {FIELDS.map(({ key, label }) => (
        <label key={key}>
          {label}
          <input
            id={key}
            value={form[key] ?? ""}
            onChange={(e) => handleChange(key, e.target.value)}
          />
        </label>
      ))}
      <button
        className="primary"
        disabled={save.isPending}
        onClick={() => save.mutate()}
      >
        {save.isPending ? "Saving…" : !dirty && save.isSuccess ? "Saved ✓" : "Save profile"}
      </button>
      {save.isError && <ErrorView error={save.error} />}
      {result.data?.updated_at && (
        <div className="mono small">last updated {result.data.updated_at}</div>
      )}
    </section>
  );
}
