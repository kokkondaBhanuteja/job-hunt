import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { EmailActionProposal } from "../../lib/api";
import { api } from "../../lib/api";
import { EMAIL_ACTION_KIND, QUERY_KEYS } from "../../lib/constants";
import { ErrorView } from "../../components/ErrorView";

interface Props {
  emailId: number;
  proposal: EmailActionProposal;
  /** Passed through to confirmAction for apply_label; sourced from EmailActions state. */
  label?: string;
  onClose: () => void;
}

// Static descriptions shown to the user before they confirm — purely informational.
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
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-modal-title"
    >
      <div className="modal">
        <h2 id="confirm-modal-title" className="modal-title">
          Confirm: {proposal.kind.replace(/_/g, " ")}
        </h2>
        <p className="muted">{ACTION_DESCRIPTIONS[proposal.kind] ?? ""}</p>

        {replyBody !== null && (
          <textarea
            className="modal-reply-body"
            readOnly
            value={replyBody}
            aria-label="Proposed reply body"
          />
        )}

        {displayLabel && (
          <div className="banner">
            Label: <strong>{displayLabel}</strong>
          </div>
        )}

        {confirmMutation.isError && <ErrorView error={confirmMutation.error} />}

        <div className="btn-row modal-actions">
          <button
            className="primary"
            onClick={() => confirmMutation.mutate()}
            disabled={confirmMutation.isPending}
          >
            {confirmMutation.isPending ? "Confirming…" : "Confirm"}
          </button>
          <button onClick={onClose} disabled={confirmMutation.isPending}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
