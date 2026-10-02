"use client";

import { useId, useState, useTransition } from "react";

import { updateEvent, type EventChanges } from "@/app/actions/events";
import { Field, FormMessage, TextAreaField } from "@/components/form";
import { ASSESSMENTS, PRIORITIES, STATUSES } from "@/lib/events";
import type { ActionState, CarcuxEvent } from "@/lib/types";

const selectCls =
  "h-11 w-full rounded-sm border border-line bg-panel-2 px-3 text-bone focus:border-steel focus:outline-none disabled:opacity-60";

/** Status, priority and assessment save on change; title, place and summary on Save. */
export function ManagePanel({ event }: { event: CarcuxEvent }) {
  const [pending, startTransition] = useTransition();
  const [result, setResult] = useState<ActionState>();
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(event.title);
  const [placeName, setPlaceName] = useState(event.place_name ?? "");
  const [summary, setSummary] = useState(event.summary ?? "");

  function save(changes: EventChanges, after?: () => void) {
    startTransition(async () => {
      const outcome = await updateEvent(event.id, changes);
      setResult(outcome);
      if (outcome?.ok) after?.();
    });
  }

  const ids = useId();
  const assessment = ASSESSMENTS.find((a) => a.value === event.assessment);

  return (
    <div className="flex flex-col gap-5" aria-busy={pending}>
      <div className="grid gap-5 sm:grid-cols-3">
        <div className="flex flex-col gap-1.5 text-sm">
          <label htmlFor={`${ids}-status`}>Status</label>
          <select
            id={`${ids}-status`}
            className={selectCls}
            value={event.status}
            disabled={pending}
            onChange={(e) => save({ status: e.target.value as CarcuxEvent["status"] })}
          >
            {STATUSES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1.5 text-sm">
          <label htmlFor={`${ids}-priority`}>Priority</label>
          <select
            id={`${ids}-priority`}
            className={selectCls}
            value={event.priority}
            disabled={pending}
            onChange={(e) => save({ priority: e.target.value as CarcuxEvent["priority"] })}
          >
            {PRIORITIES.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1.5 text-sm">
          <label htmlFor={`${ids}-assessment`}>Assessment</label>
          <select
            id={`${ids}-assessment`}
            className={selectCls}
            value={event.assessment}
            disabled={pending}
            onChange={(e) => save({ assessment: e.target.value as CarcuxEvent["assessment"] })}
          >
            {ASSESSMENTS.map((a) => (
              <option key={a.value} value={a.value}>
                {a.label}
              </option>
            ))}
          </select>
        </div>
      </div>
      {assessment && (
        <p className="-mt-2 text-sm text-steel">
          {assessment.label}: {assessment.meaning}
        </p>
      )}

      {editing ? (
        <form
          className="flex flex-col gap-4 border-l-2 border-line pl-4"
          onSubmit={(e) => {
            e.preventDefault();
            save(
              {
                title: title.trim(),
                place_name: placeName.trim() || null,
                summary: summary.trim() || null,
              },
              () => setEditing(false),
            );
          }}
        >
          <Field
            label="Title"
            required
            minLength={5}
            maxLength={160}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <Field
            label="Place name"
            maxLength={200}
            value={placeName}
            onChange={(e) => setPlaceName(e.target.value)}
          />
          <TextAreaField
            label="Summary"
            maxLength={4000}
            rows={3}
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
          />
          <div className="flex gap-3">
            <button
              type="submit"
              disabled={pending}
              className="h-11 rounded-sm bg-bone px-5 font-semibold text-ground hover:bg-white disabled:opacity-60"
            >
              {pending ? "Saving…" : "Save"}
            </button>
            <button
              type="button"
              onClick={() => setEditing(false)}
              className="h-11 rounded-sm border border-line px-4 text-steel hover:text-bone"
            >
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <button
          type="button"
          onClick={() => setEditing(true)}
          className="h-11 w-fit rounded-sm border border-line px-4 text-sm text-steel transition-colors hover:border-steel hover:text-bone"
        >
          Edit title, place and summary
        </button>
      )}
      <FormMessage state={result} />
    </div>
  );
}
