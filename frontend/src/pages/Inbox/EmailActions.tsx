import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { EmailDetail, EmailActionProposal } from "@/lib/api";
import { api } from "@/lib/api";
import { EMAIL_ACTION_KIND, QUERY_KEYS } from "@/lib/constants";
import { ErrorView } from "@/components/ErrorView";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ConfirmModal } from "./ConfirmModal";

interface Props {
  email: EmailDetail;
}

/** Action bar attached to an email detail panel.
 *  Two-step flow: Propose → show ConfirmModal → explicit Confirm sends confirm:true. */
export function EmailActions({ email }: Props) {
  const qc = useQueryClient();
  const [proposal, setProposal] = useState<EmailActionProposal | null>(null);
  const [labelValue, setLabelValue] = useState("");
  const [collectingLabel, setCollectingLabel] = useState(false);

  const proposeMutation = useMutation({
    mutationFn: ({ kind, label }: { kind: string; label?: string }) =>
      api.proposeAction(email.id, kind, label),
    onSuccess: (data) => {
      setCollectingLabel(false);
      setProposal(data);
    },
  });

  const dismissMutation = useMutation({
    mutationFn: () => api.dismissAction(email.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QUERY_KEYS.emails });
      qc.invalidateQueries({ queryKey: QUERY_KEYS.email(email.id) });
    },
  });

  function handleActionClick(kind: string) {
    if (kind === EMAIL_ACTION_KIND.APPLY_LABEL) {
      setCollectingLabel(true);
      return;
    }
    proposeMutation.mutate({ kind });
  }

  function handleLabelSubmit(ev: FormEvent<HTMLFormElement>) {
    ev.preventDefault();
    const trimmed = labelValue.trim();
    if (!trimmed) return;
    proposeMutation.mutate({ kind: EMAIL_ACTION_KIND.APPLY_LABEL, label: trimmed });
  }

  function closeModal() {
    setProposal(null);
    setLabelValue("");
  }

  const proposeBusy = proposeMutation.isPending;

  return (
    <div className="space-y-3 border-t border-border pt-4">
      {proposeMutation.isError && <ErrorView error={proposeMutation.error} />}
      {dismissMutation.isError && <ErrorView error={dismissMutation.error} />}

      {collectingLabel ? (
        <form className="space-y-2" onSubmit={handleLabelSubmit}>
          <div className="space-y-1.5">
            <Label htmlFor="action-label-input">Label name</Label>
            <Input
              id="action-label-input"
              value={labelValue}
              onChange={(ev) => setLabelValue(ev.target.value)}
              placeholder="e.g. Follow-up"
              autoFocus
            />
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="submit" size="sm" disabled={proposeBusy}>
              {proposeBusy ? "Proposing…" : "Propose label"}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => {
                setCollectingLabel(false);
                setLabelValue("");
              }}
            >
              Cancel
            </Button>
          </div>
        </form>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          <Button
            size="sm"
            variant="outline"
            onClick={() => handleActionClick(EMAIL_ACTION_KIND.DRAFT_REPLY)}
            disabled={proposeBusy}
          >
            Draft reply
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => handleActionClick(EMAIL_ACTION_KIND.APPLY_LABEL)}
            disabled={proposeBusy}
          >
            Apply label
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => handleActionClick(EMAIL_ACTION_KIND.ARCHIVE)}
            disabled={proposeBusy}
          >
            Archive
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => dismissMutation.mutate()}
            disabled={dismissMutation.isPending}
          >
            {dismissMutation.isPending ? "Dismissing…" : "Dismiss"}
          </Button>
        </div>
      )}

      {proposal && (
        <ConfirmModal
          emailId={email.id}
          proposal={proposal}
          label={labelValue || undefined}
          onClose={closeModal}
        />
      )}
    </div>
  );
}
