"use client";

import { useId, useState, useTransition } from "react";

import { judgeLink } from "@/app/actions/events";
import { ConflictPicker } from "@/components/evidence-controls";
import { CONFIDENCE, DECISION_STEPS } from "@/lib/events";
import type { ActionState, ClaimAttribute, EvidenceRelation } from "@/lib/types";

/** The guideline's decision procedure as one choice, plus confidence and staleness. */
export function JudgeForm({ evidenceId, label }: { evidenceId: string; label: string }) {
  const ids = useId();
  const [pending, startTransition] = useTransition();
  const [state, setState] = useState<ActionState>();
  const [relation, setRelation] = useState<EvidenceRelation | "">("");
  const [conflicts, setConflicts] = useState<ClaimAttribute[]>([]);
  const [confidence, setConfidence] = useState<1 | 2 | 3>(2);
  const [stale, setStale] = useState(false);
  const [note, setNote] = useState("");

  const ready = relation !== "" && (relation !== "partially_supports" || conflicts.length > 0);

  return (
    <form
      className="flex flex-col gap-3"
      aria-busy={pending}
      onSubmit={(e) => {
        e.preventDefault();
        if (!relation) return;
        startTransition(async () =>
          setState(
            await judgeLink(evidenceId, relation, {
              conflicts: relation === "partially_supports" ? conflicts : [],
              confidence,
              stale,
              note,
            }),
          ),
        );
      }}
    >
      <fieldset>
        <legend className="mb-2 text-sm font-semibold">{label}</legend>
        <div className="flex flex-col gap-1.5">
          {DECISION_STEPS.map((step, i) => (
            <label
              key={step.value}
              htmlFor={`${ids}-${step.value}`}
              className={`flex cursor-pointer items-start gap-2.5 rounded-lg border px-3 py-2 text-sm transition-colors ${
                relation === step.value
                  ? "border-brand bg-brand-soft"
                  : "border-line bg-panel hover:border-muted"
              }`}
            >
              <input
                id={`${ids}-${step.value}`}
                type="radio"
                name={`${ids}-relation`}
                value={step.value}
                checked={relation === step.value}
                onChange={() => setRelation(step.value)}
                className="mt-0.5 h-4 w-4 accent-[var(--color-brand)]"
              />
              <span>
                <span className="block text-xs text-muted">
                  {i + 1}. {step.question}
                </span>
                {step.answer}
              </span>
            </label>
          ))}
        </div>
      </fieldset>
      {relation === "partially_supports" && (
        <ConflictPicker
          value={conflicts}
          onChange={setConflicts}
          legend="What does it get wrong?"
        />
      )}
      <div className="flex flex-wrap items-center gap-4 text-sm">
        <label htmlFor={`${ids}-conf`} className="flex items-center gap-2">
          How sure
          <select
            id={`${ids}-conf`}
            value={confidence}
            onChange={(e) => setConfidence(Number(e.target.value) as 1 | 2 | 3)}
            className="h-9 rounded-md border border-line bg-panel px-2"
          >
            {CONFIDENCE.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
        </label>
        <label htmlFor={`${ids}-stale`} className="flex items-center gap-1.5 text-muted">
          <input
            id={`${ids}-stale`}
            type="checkbox"
            checked={stale}
            onChange={(e) => setStale(e.target.checked)}
            className="h-4 w-4 accent-[var(--color-brand)]"
          />
          Out of date when published
        </label>
      </div>
      <label htmlFor={`${ids}-note`} className="sr-only">
        Note
      </label>
      <input
        id={`${ids}-note`}
        value={note}
        onChange={(e) => setNote(e.target.value)}
        maxLength={2000}
        placeholder="Note (optional): what decided it"
        className="h-9 rounded-md border border-line bg-panel px-3 text-sm"
      />
      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={pending || !ready}
          className="h-10 rounded-lg bg-brand px-4 font-semibold text-white hover:bg-brand-strong disabled:cursor-not-allowed disabled:opacity-50"
        >
          {pending ? "Saving…" : "Save my judgement"}
        </button>
        {state && !state.ok && (
          <p role="alert" className="text-sm text-critical">
            {state.message}
          </p>
        )}
      </div>
    </form>
  );
}
