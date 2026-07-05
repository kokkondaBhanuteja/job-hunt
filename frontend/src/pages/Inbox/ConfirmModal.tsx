import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { EmailActionProposal } from "@/lib/api";
import { api } from "@/lib/api";
import { EMAIL_ACTION_KIND, QUERY_KEYS } from "@/lib/constants";
import { ErrorView } from "@/components/ErrorView";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";

interface Props {
  emailId: number;
  proposal: EmailActionProposal;
  label?: string;
  onClose: () => void;
}

const ACTION_DESCRIPTIONS: Record<string, string> = {
  [EMAIL_ACTION_KIND.DRAFT_REPLY]:
    "A draft will be saved to your Gmail Drafts — nothing is sent.",
  [EMAIL_ACTION_KIND.ARCHIVE]:
    "This email will be archived (removed from Inbox — reversible).",
  [EMAIL_ACTION_KIND.APPLY_LABEL]: "This label will be applied to the email in Gmail.",
};

/** Modal that shows the proposed action and requires an explicit Confirm click.
 *  confirm:true is sent ONLY from the Confirm button — never speculatively. */
export function ConfirmModal({ emailId, proposal, label, onClose }: Props) {
  const qc = useQueryClient();

  const confirmMutation = useMutation({
    mutationFn: () =>
      api.confirmAction(emailId, {
        kind: proposal.kind,
        action_id: proposal.action_id,
        confirm: true,
        label: label ?? null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QUERY_KEYS.emails });
      qc.invalidateQueries({ queryKey: QUERY_KEYS.email(emailId) });
      onClose();
    },
  });

  const replyBody =
    proposal.kind === EMAIL_ACTION_KIND.DRAFT_REPLY
      ? (proposal.payload?.["reply_body"] ?? "")
      : null;

  const displayLabel =
    proposal.kind === EMAIL_ACTION_KIND.APPLY_LABEL
      ? (proposal.payload?.["label"] ?? label ?? "")
      : null;

  return (
    <Dialog open onOpenChange={(open) => !open && !confirmMutation.isPending && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="capitalize">
            Confirm: {proposal.kind.replace(/_/g, " ")}
          </DialogTitle>
          <DialogDescription>{ACTION_DESCRIPTIONS[proposal.kind] ?? ""}</DialogDescription>
        </DialogHeader>

        {replyBody !== null && (
          <Textarea
            readOnly
            value={replyBody}
            aria-label="Proposed reply body"
            className="min-h-[160px]"
          />
        )}

        {displayLabel && (
          <div className="rounded-md border border-border bg-secondary/50 px-3 py-2 text-sm">
            Label: <strong>{displayLabel}</strong>
          </div>
        )}

        {confirmMutation.isError && <ErrorView error={confirmMutation.error} />}

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={confirmMutation.isPending}>
            Cancel
          </Button>
          <Button onClick={() => confirmMutation.mutate()} disabled={confirmMutation.isPending}>
            {confirmMutation.isPending ? "Confirming…" : "Confirm"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
