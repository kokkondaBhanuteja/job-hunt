import type { ApplyPolicy } from "../lib/api";
import { EmptyView } from "../components/EmptyView";

interface Props {
  policy: ApplyPolicy;
}

/** Read-only display of the parsed apply policy returned by the backend. */
export function ApplyPolicyView({ policy }: Props) {
  const isEmpty =
    policy.must_have.length === 0 && policy.avoid.length === 0 && !policy.seniority;

  if (isEmpty) {
    return (
      <EmptyView>No apply policy parsed yet — save preferences above to generate one.</EmptyView>
    );
  }

  return (
    <div>
      <dl className="kv">
        <div>
          <dt>Min fit score</dt>
          <dd>{policy.min_fit_score}</dd>
        </div>
        {policy.seniority && (
          <div>
            <dt>Seniority</dt>
            <dd>{policy.seniority}</dd>
          </div>
        )}
        <div>
          <dt>Remote only</dt>
          <dd>{policy.remote_only ? "Yes" : "No"}</dd>
        </div>
      </dl>
      {policy.must_have.length > 0 && (
        <div>
          <h3>Must have</h3>
          <div className="chips">
            {policy.must_have.map((item) => (
              <span key={item} className="chip">{item}</span>
            ))}
          </div>
        </div>
      )}
      {policy.avoid.length > 0 && (
        <div>
          <h3>Avoid</h3>
          <ul className="brief-list">
            {policy.avoid.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
