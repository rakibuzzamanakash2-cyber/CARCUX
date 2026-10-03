"use client";

import { useId, useState, useTransition } from "react";

import { changeRelation, linkReport, unlinkEvidence } from "@/app/actions/events";
import { linkSignal } from "@/app/actions/signals";
import { CLAIM_ATTRIBUTES, claimLabel, CONFIDENCE, RELATIONS } from "@/lib/events";
import type { ActionState, ClaimAttribute, EvidenceRelation } from "@/lib/types";

const smallBtn =
  "h-9 rounded-md border px-3 text-sm font-semibold shadow-sm transition-colors disabled:cursor-wait disabled:opacity-60";

function Result({ state }: { state: ActionState }) {
  if (!state || state.ok) return null;
  return (
    <p role="alert" className="text-sm text-critical">
      {state.message}
    </p>
  );
}

/** "Partly supports" needs to say what the item gets wrong (the dataset's conflicts). */
function ConflictPicker({
  value,
  onChange,
  legend,
}: {
  value: ClaimAttribute[];
  onChange: (next: ClaimAttribute[]) => void;
  legend: string;
}) {
  const id = useId();
  return (
    <fieldset className="rounded-lg border border-alert/40 bg-alert-soft/40 p-3">
      <legend className="px-1 text-sm font-semibold">{legend}</legend>
      <div className="mt-1 grid gap-x-4 gap-y-1.5 sm:grid-cols-2">
        {CLAIM_ATTRIBUTES.map((a) => (
          <label
            key={a.value}
            htmlFor={`${id}-${a.value}`}
            className="flex items-center gap-2 text-sm"
          >
            <input
              id={`${id}-${a.value}`}
              type="checkbox"
              checked={value.includes(a.value)}
              onChange={(e) =>
                onChange(
                  e.target.checked ? [...value, a.value] : value.filter((v) => v !== a.value),
                )
              }
              className="h-4 w-4 accent-[var(--color-brand)]"
            />
            {a.label}
          </label>
        ))}
      </div>
    </fieldset>
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
  const [partial, setPartial] = useState(false);
  const [conflicts, setConflicts] = useState<ClaimAttribute[]>([]);

  function link(relation: EvidenceRelation, chosen: ClaimAttribute[] = []) {
    startTransition(async () =>
      setState(
        signalId
          ? await linkSignal(eventId, signalId, relation, chosen)
          : await linkReport(eventId, reportId ?? "", relation, { conflicts: chosen }),
      ),
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <div role="group" aria-label={label} className="flex flex-wrap gap-2">
        {RELATIONS.map((r) => (
          <button
            key={r.value}
            type="button"
            disabled={pending}
            aria-expanded={r.value === "partially_supports" ? partial : undefined}
            onClick={() =>
              r.value === "partially_supports" ? setPartial((v) => !v) : link(r.value)
            }
            className={`${smallBtn} ${
              r.value === "partially_supports" && partial
                ? "border-alert bg-alert-soft text-ink"
                : "border-line bg-panel text-ink hover:border-brand hover:text-brand"
            }`}
          >
            {r.label}
          </button>
        ))}
      </div>
      {partial && (
        <div className="flex flex-col gap-2">
          <ConflictPicker
            value={conflicts}
            onChange={setConflicts}
            legend="What does it get wrong?"
          />
          <div className="flex gap-2">
            <button
              type="button"
              disabled={pending || conflicts.length === 0}
              onClick={() => link("partially_supports", conflicts)}
              className={`${smallBtn} border-brand bg-brand text-white hover:bg-brand-strong`}
            >
              Link as partly supports
            </button>
            <button
              type="button"
              onClick={() => setPartial(false)}
              className={`${smallBtn} border-line bg-panel text-ink`}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
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
  conflicts = [],
  stale = false,
  confidence = 2,
  noun = "report",
}: {
  eventId: string;
  evidenceId: string;
  reportId?: string;
  relation: EvidenceRelation;
  conflicts?: ClaimAttribute[];
  stale?: boolean;
  confidence?: 1 | 2 | 3;
  noun?: "report" | "signal";
}) {
  const [pending, startTransition] = useTransition();
  const [state, setState] = useState<ActionState>();
  // Choosing "partly supports" waits for the conflicts before saving.
  const [draft, setDraft] = useState<ClaimAttribute[] | null>(null);
  // Shown at once, put back if the save fails.
  const [sure, setSure] = useState(confidence);
  const [old, setOld] = useState(stale);
  const id = useId();

  function save(
    rel?: EvidenceRelation,
    labels?: Parameters<typeof changeRelation>[4],
    undo?: () => void,
  ) {
    startTransition(async () => {
      const result = await changeRelation(eventId, evidenceId, reportId, rel, labels);
      setState(result);
      if (result?.ok) setDraft(null);
      else undo?.();
    });
  }

  const selectCls =
    "h-9 rounded-md border border-line bg-panel px-2 text-sm text-ink shadow-sm focus:border-brand focus:outline-none disabled:opacity-60";

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-3">
        <label className="sr-only" htmlFor={`rel-${evidenceId}`}>
          How this {noun} bears on the event
        </label>
        <select
          id={`rel-${evidenceId}`}
          value={draft ? "partially_supports" : relation}
          disabled={pending}
          onChange={(e) => {
            const next = e.target.value as EvidenceRelation;
            if (next === "partially_supports") setDraft(conflicts);
            else {
              setDraft(null);
              save(next);
            }
          }}
          className={selectCls}
        >
          {RELATIONS.map((r) => (
            <option key={r.value} value={r.value}>
              {r.label}
            </option>
          ))}
        </select>
        <label className="sr-only" htmlFor={`${id}-conf`}>
          How sure you are about this {noun}
        </label>
        <select
          id={`${id}-conf`}
          value={sure}
          disabled={pending}
          onChange={(e) => {
            const next = Number(e.target.value) as 1 | 2 | 3;
            setSure(next);
            save(undefined, { confidence: next }, () => setSure(confidence));
          }}
          className={selectCls}
          title="How sure you are"
        >
          {CONFIDENCE.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </select>
        <label htmlFor={`${id}-stale`} className="flex items-center gap-1.5 text-sm text-muted">
          <input
            id={`${id}-stale`}
            type="checkbox"
            checked={old}
            disabled={pending}
            onChange={(e) => {
              const next = e.target.checked;
              setOld(next);
              save(undefined, { stale: next }, () => setOld(stale));
            }}
            className="h-4 w-4 accent-[var(--color-brand)]"
          />
          Out of date when published
        </label>
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
      {!draft && relation === "partially_supports" && (
        <p className="text-sm">
          <span className="text-muted">Gets wrong: </span>
          {conflicts.length ? (
            conflicts.map(claimLabel).join(", ")
          ) : (
            <span className="font-semibold text-critical">
              not recorded yet; choose Partly supports again to say what
            </span>
          )}
          <button
            type="button"
            onClick={() => setDraft(conflicts)}
            className="ml-2 font-semibold text-brand hover:underline"
          >
            Change
          </button>
        </p>
      )}
      {draft && (
        <div className="flex flex-col gap-2">
          <ConflictPicker value={draft} onChange={setDraft} legend="What does it get wrong?" />
          <div className="flex gap-2">
            <button
              type="button"
              disabled={pending || draft.length === 0}
              onClick={() => save("partially_supports", { conflicts: draft })}
              className={`${smallBtn} border-brand bg-brand text-white hover:bg-brand-strong`}
            >
              Save
            </button>
            <button
              type="button"
              onClick={() => setDraft(null)}
              className={`${smallBtn} border-line bg-panel text-ink`}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
      <Result state={state} />
    </div>
  );
}
