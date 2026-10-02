"use client";

import { useState, useTransition } from "react";

import { changeRelation, linkReport, unlinkEvidence } from "@/app/actions/events";
import { RELATIONS } from "@/lib/events";
import type { ActionState, EvidenceRelation } from "@/lib/types";

function Result({ state }: { state: ActionState }) {
  if (!state || state.ok) return null;
  return (
    <p role="alert" className="text-sm text-signal">
      {state.message}
    </p>
  );
}

/** One-click link of a report to an event, choosing how it bears on the event. */
export function LinkButtons({
  eventId,
  reportId,
  label,
}: {
  eventId: string;
  reportId: string;
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
              startTransition(async () => setState(await linkReport(eventId, reportId, r.value)))
            }
            className="h-9 rounded-sm border border-line px-3 text-sm text-bone transition-colors hover:border-steel hover:bg-panel-2 disabled:cursor-wait disabled:opacity-60"
          >
            {r.label}
          </button>
        ))}
      </div>
      <Result state={state} />
    </div>
  );
}

/** Change how a linked report bears on the event, or unlink it. */
export function EvidenceControls({
  eventId,
  evidenceId,
  reportId,
  relation,
}: {
  eventId: string;
  evidenceId: string;
  reportId: string;
  relation: EvidenceRelation;
}) {
  const [pending, startTransition] = useTransition();
  const [state, setState] = useState<ActionState>();
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex flex-wrap items-center gap-3">
        <label className="sr-only" htmlFor={`rel-${evidenceId}`}>
          How this report bears on the event
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
          className="h-9 rounded-sm border border-line bg-panel-2 px-2 text-sm text-bone focus:border-steel focus:outline-none disabled:opacity-60"
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
            if (!window.confirm("Unlink this report from the event? It stays in Field reports."))
              return;
            startTransition(async () =>
              setState(await unlinkEvidence(eventId, evidenceId, reportId)),
            );
          }}
          className="text-sm text-steel underline-offset-2 hover:text-bone hover:underline disabled:opacity-60"
        >
          Unlink
        </button>
      </div>
      <Result state={state} />
    </div>
  );
}
