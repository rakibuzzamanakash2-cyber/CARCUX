"use client";

import { RotateCcw, Sparkles } from "lucide-react";
import { useState, useTransition } from "react";

import { deactivateAssessment, trainAssessment } from "@/app/actions/assessment";
import type { ActionState } from "@/lib/types";

/** Train (or retrain) the assessment model, or go back to the starting assumptions. Admins only. */
export function AssessmentModelControls({
  active,
  canTrain,
}: {
  active: boolean;
  canTrain: boolean;
}) {
  const [pending, startTransition] = useTransition();
  const [state, setState] = useState<ActionState>();

  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        disabled={pending || !canTrain}
        onClick={() => startTransition(async () => setState(await trainAssessment()))}
        className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-brand px-4 font-semibold text-white hover:bg-brand-strong disabled:cursor-not-allowed disabled:opacity-50"
      >
        <Sparkles size={17} aria-hidden="true" />
        {pending ? "Training…" : active ? "Retrain on resolved events" : "Train and switch on"}
      </button>
      {active && (
        <button
          type="button"
          disabled={pending}
          onClick={() => startTransition(async () => setState(await deactivateAssessment()))}
          className="inline-flex items-center justify-center gap-2 text-sm font-semibold text-brand hover:underline disabled:opacity-50"
        >
          <RotateCcw size={15} aria-hidden="true" />
          Go back to the starting assumptions
        </button>
      )}
      <p
        role="status"
        aria-live="polite"
        className={`text-sm ${state?.ok === false ? "text-red" : "text-muted"}`}
      >
        {state?.message}
      </p>
    </div>
  );
}
