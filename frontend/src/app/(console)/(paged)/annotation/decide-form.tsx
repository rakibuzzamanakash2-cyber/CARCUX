"use client";

import { useId, useState, useTransition } from "react";

import { adjudicateLink } from "@/app/actions/events";
import { ConflictPicker } from "@/components/evidence-controls";
import { RELATIONS } from "@/lib/events";
import type { ActionState, ClaimAttribute, EvidenceRelation } from "@/lib/types";

/** Resolve a disagreement into the gold label (guideline 7.3). */
export function DecideForm({
  evidenceId,
  options,
}: {
  evidenceId: string;
  options: EvidenceRelation[];
}) {
  const ids = useId();
  const [pending, startTransition] = useTransition();
  const [state, setState] = useState<ActionState>();
  const [relation, setRelation] = useState<EvidenceRelation | "">("");
  const [conflicts, setConflicts] = useState<ClaimAttribute[]>([]);
  const [note, setNote] = useState("");
  const ready = relation !== "" && (relation !== "partially_supports" || conflicts.length > 0);
  // The annotators' labels first, then the rest.
  const ordered = [
    ...options,
    ...RELATIONS.map((r) => r.value).filter((v) => !options.includes(v)),
  ];

  return (
    <form
      className="flex flex-col gap-3 rounded-lg bg-panel-2/60 p-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (!relation) return;
        startTransition(async () =>
          setState(
            await adjudicateLink(
              evidenceId,
              relation,
              relation === "partially_supports" ? conflicts : [],
              note,
            ),
          ),
        );
      }}
    >
      <div className="flex flex-wrap items-end gap-3">
        <label htmlFor={`${ids}-gold`} className="flex flex-col gap-1 text-sm font-semibold">
          Final label
          <select
            id={`${ids}-gold`}
            value={relation}
            onChange={(e) => setRelation(e.target.value as EvidenceRelation)}
            className="h-10 rounded-md border border-line bg-panel px-2 font-normal"
          >
            <option value="">Choose…</option>
            {ordered.map((v) => (
              <option key={v} value={v}>
                {RELATIONS.find((r) => r.value === v)?.label}
                {options.includes(v) ? " (given by an annotator)" : ""}
              </option>
            ))}
          </select>
        </label>
        <label
          htmlFor={`${ids}-note`}
          className="flex min-w-60 flex-1 flex-col gap-1 text-sm font-semibold"
        >
          Why
          <input
            id={`${ids}-note`}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            maxLength={2000}
            placeholder="Optional: the rule that settled it"
            className="h-10 rounded-md border border-line bg-panel px-3 font-normal"
          />
        </label>
        <button
          type="submit"
          disabled={pending || !ready}
          className="h-10 rounded-lg bg-brand px-4 font-semibold text-white hover:bg-brand-strong disabled:cursor-not-allowed disabled:opacity-50"
        >
          {pending ? "Saving…" : "Save decision"}
        </button>
      </div>
      {relation === "partially_supports" && (
        <ConflictPicker
          value={conflicts}
          onChange={setConflicts}
          legend="What does it get wrong?"
        />
      )}
      {state && !state.ok && (
        <p role="alert" className="text-sm text-critical">
          {state.message}
        </p>
      )}
    </form>
  );
}
