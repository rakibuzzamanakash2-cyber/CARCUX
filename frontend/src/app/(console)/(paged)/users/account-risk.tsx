import { Panel } from "@/components/page-header";
import type { AccountRisk } from "@/lib/types";

const REVIEW_FROM = 0.5;

/** Field workers whose last day looks unlike their own history. A reason to talk with
 * the worker, never an automatic block. */
export function AccountRiskPanel({ risks }: { risks: AccountRisk[] }) {
  const marked = risks.filter((r) => r.score >= REVIEW_FROM);
  const quiet = risks.filter((r) => r.recent === 0).length;
  return (
    <Panel
      id="risk"
      title="Field workers to check on"
      description={`Compares each field worker's last 24 hours with their own earlier weeks: where they report from, how many reports, at what hours, and how many carry integrity flags. A high score is a reason to talk with the worker, never proof of misuse. ${quiet} sent nothing in the last day.`}
    >
      {marked.length === 0 ? (
        <p className="text-sm text-steel">No field worker looks unusual in the last day.</p>
      ) : (
        <ul className="divide-y divide-line">
          {marked.map((r) => (
            <li key={r.user_id} className="py-3">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span className="font-medium">{r.full_name}</span>
                <span className="text-sm text-steel">
                  Score <span className="font-semibold text-critical">{r.score.toFixed(2)}</span>
                  {" · "}
                  {r.recent} {r.recent === 1 ? "report" : "reports"} in the last day, {r.baseline}{" "}
                  earlier
                </span>
              </div>
              <ul className="mt-1 list-disc pl-5 text-sm">
                {r.reasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
