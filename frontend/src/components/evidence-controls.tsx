"use client";

import { useState, useTransition } from "react";

import { changeRelation, linkReport, unlinkEvidence } from "@/app/actions/events";
import { linkSignal } from "@/app/actions/signals";
import { RELATIONS } from "@/lib/events";
import type { ActionState, EvidenceRelation } from "@/lib/types";

function Result({ state }: { state: ActionState }) {
  if (!state || state.ok) return null;
  return (
    <p role="alert" className="text-sm text-critical">
      {state.message}
    </p>
  );
}

/** One-click link of a report or a signal to an event, choosing how it bears on the event. */
export function LinkButtons({
  eventId,
  reportId,
  signalId,
  label,
}: {
  eventId: string;
  reportId?: string;
  signalId?: string;
  label: string;
}) {
  const [pending, startTransition] = useTransition();
  const [state, setState] = useState<ActionState>();
  return (
    <div className="flex flex-col gap-1.5">
      <div role="group" aria-label={label} className="flex flex-wrap gap-2">
        {RELATIONS.map((r) => (
          <button
            key={r.value}
            type="button"
            disabled={pending}
            onClick={() =>
              startTransition(async () =>
                setState(
                  signalId
                    ? await linkSignal(eventId, signalId, r.value)
                    : await linkReport(eventId, reportId ?? "", r.value),
                ),
              )
            }
            className="h-9 rounded-md border border-line bg-panel px-3 text-sm font-semibold text-ink shadow-sm transition-colors hover:border-brand hover:text-brand disabled:cursor-wait disabled:opacity-60"
          >
            {r.label}
          </button>
        ))}
      </div>
      <Result state={state} />
    </div>
  );
}

/** Change how a linked report or signal bears on the event, or unlink it. */
export function EvidenceControls({
  eventId,
  evidenceId,
  reportId = "",
  relation,
  noun = "report",
}: {
  eventId: string;
  evidenceId: string;
  reportId?: string;
  relation: EvidenceRelation;
  noun?: "report" | "signal";
}) {
  const [pending, startTransition] = useTransition();
  const [state, setState] = useState<ActionState>();
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex flex-wrap items-center gap-3">
        <label className="sr-only" htmlFor={`rel-${evidenceId}`}>
          How this {noun} bears on the event
        </label>
        <select
          id={`rel-${evidenceId}`}
          value={relation}
          disabled={pending}
          onChange={(e) =>
            startTransition(async () =>
              setState(
                await changeRelation(
                  eventId,
                  evidenceId,
                  reportId,
                  e.target.value as EvidenceRelation,
                ),
              ),
            )
          }
          className="h-9 rounded-md border border-line bg-panel px-2 text-sm text-ink shadow-sm focus:border-brand focus:outline-none disabled:opacity-60"
        >
          {RELATIONS.map((r) => (
            <option key={r.value} value={r.value}>
              {r.label}
            </option>
          ))}
        </select>
        <button
          type="button"
          disabled={pending}
          onClick={() => {
            const home = noun === "signal" ? "Signals" : "Field reports";
            if (!window.confirm(`Unlink this ${noun} from the event? It stays in ${home}.`)) return;
            startTransition(async () =>
              setState(await unlinkEvidence(eventId, evidenceId, reportId)),
            );
          }}
          className="text-sm text-muted underline-offset-2 hover:text-ink hover:underline disabled:opacity-60"
        >
          Unlink
        </button>
      </div>
      <Result state={state} />
    </div>
  );
}
