import { suggestionReasons } from "@/lib/suggestions";
import type { CandidateEvent } from "@/lib/types";

/** The model's match estimate (when there is one) and the reasons for a suggestion. */
export function SuggestionMeta({ c, small = false }: { c: CandidateEvent; small?: boolean }) {
  const reasons = suggestionReasons(c);
  return (
    <p
      className={`flex flex-wrap items-center gap-x-3 gap-y-1 text-muted ${small ? "text-xs" : "text-sm"}`}
    >
      {c.method === "model" && c.score !== null && (
        <span
          className="rounded-full border border-brand/40 bg-brand-soft px-2 py-0.5 text-xs font-semibold text-brand"
          title="The suggestion model's estimate that this report is about this event"
        >
          {Math.round(c.score * 100)}% match
        </span>
      )}
      {reasons.map((r) => (
        <span key={r} className={r === "same type" ? "font-semibold text-brand" : undefined}>
          {r}
        </span>
      ))}
    </p>
  );
}
