import type { EmailSummary } from "../../lib/api";

interface Props {
  email: EmailSummary;
  active: boolean;
  onSelect: () => void;
}

/** One selectable email in the inbox list: category chip, subject, sender, date. */
export function EmailRow({ email, active, onSelect }: Props) {
  return (
    <button className={active ? "card active" : "card"} onClick={onSelect}>
      <div className="card-top">
        <span className="chip">{(email.category ?? "uncategorized").replace(/_/g, " ")}</span>
        <span className="mono">{(email.received_at ?? "").slice(0, 10)}</span>
      </div>
      <div className="title">{email.subject ?? "(no subject)"}</div>
      <div className="loc">{email.from_name ?? email.from_addr ?? "unknown sender"}</div>
    </button>
  );
}
