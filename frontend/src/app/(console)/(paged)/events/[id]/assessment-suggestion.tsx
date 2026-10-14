"use client";

import { Check, X } from "lucide-react";
import { useState, useTransition } from "react";

import { updateEvent } from "@/app/actions/events";
import { AssessmentText } from "@/components/event-badges";
import { FormMessage } from "@/components/form";
import { assessmentLabel, claimLabel } from "@/lib/events";
import type { ActionState, AssessmentSuggestion, CarcuxEvent } from "@/lib/types";

const KIND: Record<string, string> = {
  field: "field worker",
  news: "news",
  public_record: "public record",
  other: "other source",
};

function plural(n: number, one: string, many: string) {
  return `${n} ${n === 1 ? one : many}`;
}

/** The system's suggested assessment, why, and a button to take it. The analyst decides. */
export function AssessmentSuggestionPanel({
  event,
  suggestion: s,
}: {
  event: CarcuxEvent;
  suggestion: AssessmentSuggestion;
}) {
  const [pending, startTransition] = useTransition();
  const [result, setResult] = useState<ActionState>();
  const same = event.assessment === s.label;
  const total = s.sources_supporting + s.sources_denying;

  return (
    <div className="flex flex-col gap-3 text-sm" aria-busy={pending}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-base font-semibold">
          <AssessmentText assessment={s.label} />
        </span>
        {s.probability !== null && (
          <span className="text-muted">
            <strong className="text-ink">{Math.round(s.probability * 100)}%</strong> likely it
            happened
          </span>
        )}
      </div>

      {total === 0 ? (
        <p className="text-muted">
          No linked report or signal says whether it happened yet. Link evidence under Evidence.
        </p>
      ) : (
        <p>
          From {plural(total, "source", "sources")}: {s.sources_supporting}{" "}
          {s.sources_supporting === 1 ? "says" : "say"} it happened, {s.sources_denying}{" "}
          {s.sources_denying === 1 ? "says" : "say"} it did not
          {s.credible_supporting + s.credible_denying < total &&
            ` (credible: ${s.credible_supporting} and ${s.credible_denying})`}
          .
        </p>
      )}
      {s.disputed.length > 0 && (
        <p>
          <span className="text-muted">Details in dispute:</span>{" "}
          {s.disputed.map(claimLabel).join(", ")}
        </p>
      )}

      {s.reasons.length > 0 && (
        <div>
          <p className="mb-1.5 text-muted">Weighed most</p>
          <ul className="flex flex-col gap-1.5">
            {s.reasons.map((r, i) => (
              <li key={`${r.source}-${i}`} className="flex items-start gap-2">
                {r.vote > 0 ? (
                  <Check
                    size={16}
                    className="mt-0.5 shrink-0 text-ok"
                    aria-label="says it happened"
                  />
                ) : (
                  <X
                    size={16}
                    className="mt-0.5 shrink-0 text-critical"
                    aria-label="says it did not"
                  />
                )}
                <span className="min-w-0">
                  <span className="font-semibold">{r.source}</span>
                  <span className="text-muted">
                    {" "}
                    · {KIND[r.kind] ?? r.kind} · right {Math.round(r.reliability * 100)}% of the
                    time {r.learned ? "(its own record)" : "(assumed for its kind)"}
                    {r.disputed.length > 0 &&
                      ` · wrong on ${r.disputed.map(claimLabel).join(", ").toLowerCase()}`}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {same ? (
        <p className="text-muted">This is the current assessment.</p>
      ) : (
        <button
          type="button"
          disabled={pending}
          onClick={() =>
            startTransition(async () =>
              setResult(await updateEvent(event.id, { assessment: s.label })),
            )
          }
          className="h-10 w-fit rounded-md border border-brand px-4 font-semibold text-brand hover:bg-brand-soft disabled:opacity-60"
        >
          {pending ? "Saving…" : `Set to ${assessmentLabel(s.label).toLowerCase()}`}
        </button>
      )}
      <FormMessage state={result} />
      <p className="text-xs text-muted">
        {s.method === "model"
          ? "From each source's record on events whose outcome is known."
          : "From starting assumptions about each kind of source, until an admin trains a model on events with ground truth."}{" "}
        A suggestion only: you decide, and the history records whether it was followed.
      </p>
    </div>
  );
}
