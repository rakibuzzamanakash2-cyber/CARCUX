"use client";

import { ExternalLink, Trash2 } from "lucide-react";
import { useId, useState, useTransition } from "react";

import { updateEvent } from "@/app/actions/events";
import { formatDhaka, DHAKA_OFFSET } from "@/lib/format";
import { GROUND_TRUTH_KINDS } from "@/lib/events";
import type { ActionState, CarcuxEvent, GroundTruthKind, GroundTruthSource } from "@/lib/types";

const inputCls =
  "h-10 w-full rounded-md border border-line bg-panel px-3 text-ink shadow-sm focus:border-brand focus:outline-none disabled:opacity-60";

const OCCURRED = [
  { value: "", label: "Not established yet" },
  { value: "yes", label: "Yes, it happened" },
  { value: "no", label: "No, it did not happen" },
];

/** Did it happen, and which post-event sources say so. Each change saves at once. */
export function GroundTruthPanel({ event }: { event: CarcuxEvent }) {
  const [pending, startTransition] = useTransition();
  const [state, setState] = useState<ActionState>();
  const [reference, setReference] = useState("");
  const [publishedAt, setPublishedAt] = useState("");
  const [kind, setKind] = useState<GroundTruthKind>("news_followup");
  const [note, setNote] = useState(event.ground_truth_note ?? "");
  const ids = useId();

  function save(changes: Parameters<typeof updateEvent>[1], after?: () => void) {
    startTransition(async () => {
      const result = await updateEvent(event.id, changes);
      setState(result);
      if (result?.ok) after?.();
    });
  }

  const sources = event.ground_truth_sources;
  const occurred = event.occurred === null ? "" : event.occurred ? "yes" : "no";
  const ready = event.occurred !== null && sources.length > 0;

  function addSource(e: React.FormEvent) {
    e.preventDefault();
    if (!/^\d{4}-\d{2}-\d{2}$/.test(publishedAt)) {
      setState({ ok: false, message: "Enter the date the source was published." });
      return;
    }
    const next: GroundTruthSource = {
      reference: reference.trim(),
      published_at: `${publishedAt}T12:00:00${DHAKA_OFFSET}`,
      kind,
    };
    save({ ground_truth_sources: [...sources, next] }, () => {
      setReference("");
      setPublishedAt("");
    });
  }

  return (
    <div className="flex flex-col gap-5 text-sm" aria-busy={pending}>
      <p
        className={`rounded-md px-3 py-2 font-semibold ${
          ready ? "bg-brand-soft text-brand" : "bg-alert-soft text-alert"
        }`}
      >
        {ready
          ? "Ready for the dataset."
          : "Not in the dataset yet: say whether it happened and add a source."}
      </p>

      <div className="flex flex-col gap-1.5">
        <label htmlFor={`${ids}-occ`}>Did it happen?</label>
        <select
          id={`${ids}-occ`}
          className={inputCls}
          value={occurred}
          disabled={pending}
          onChange={(e) =>
            save({ occurred: e.target.value === "" ? null : e.target.value === "yes" })
          }
        >
          {OCCURRED.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-2">
        <p className="font-semibold">Sources published afterwards</p>
        {sources.length === 0 ? (
          <p className="text-muted">None yet.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {sources.map((s, i) => (
              <li
                key={`${s.reference}-${i}`}
                className="flex items-start justify-between gap-2 rounded-md border border-line p-2"
              >
                <span className="min-w-0">
                  <a
                    href={s.reference}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex max-w-full items-center gap-1 font-semibold break-all text-brand hover:underline"
                  >
                    {s.reference.replace(/^https?:\/\/(www\.)?/, "").slice(0, 60)}
                    <ExternalLink size={12} aria-hidden="true" className="shrink-0" />
                  </a>
                  <span className="block text-xs text-muted">
                    {GROUND_TRUTH_KINDS.find((k) => k.value === s.kind)?.label},{" "}
                    {formatDhaka(s.published_at).split(",")[0]}
                  </span>
                </span>
                <button
                  type="button"
                  disabled={pending}
                  onClick={() => save({ ground_truth_sources: sources.filter((_, j) => j !== i) })}
                  className="rounded p-1 text-muted hover:bg-red-soft hover:text-red"
                >
                  <Trash2 size={15} aria-hidden="true" />
                  <span className="sr-only">Remove source {i + 1}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
        <form onSubmit={addSource} className="flex flex-col gap-2 rounded-md bg-panel-2/60 p-3">
          <label htmlFor={`${ids}-ref`} className="text-xs font-semibold">
            Link to the source
          </label>
          <input
            id={`${ids}-ref`}
            type="url"
            required
            placeholder="https://"
            value={reference}
            onChange={(e) => setReference(e.target.value)}
            className={inputCls}
          />
          <div className="grid grid-cols-2 gap-2">
            <div className="flex flex-col gap-1">
              <label htmlFor={`${ids}-date`} className="text-xs font-semibold">
                Published on
              </label>
              <input
                id={`${ids}-date`}
                type="date"
                required
                value={publishedAt}
                onChange={(e) => setPublishedAt(e.target.value)}
                className={inputCls}
              />
            </div>
            <div className="flex flex-col gap-1">
              <label htmlFor={`${ids}-kind`} className="text-xs font-semibold">
                Kind
              </label>
              <select
                id={`${ids}-kind`}
                value={kind}
                onChange={(e) => setKind(e.target.value as GroundTruthKind)}
                className={inputCls}
              >
                {GROUND_TRUTH_KINDS.map((k) => (
                  <option key={k.value} value={k.value}>
                    {k.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <button
            type="submit"
            disabled={pending}
            className="h-9 rounded-md border border-brand bg-panel px-3 font-semibold text-brand hover:bg-brand-soft disabled:opacity-60"
          >
            Add source
          </button>
        </form>
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor={`${ids}-note`}>Note</label>
        <textarea
          id={`${ids}-note`}
          rows={2}
          maxLength={2000}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Optional: where sources disagree, or what is still uncertain"
          className="rounded-md border border-line bg-panel px-3 py-2 text-ink shadow-sm focus:border-brand focus:outline-none"
        />
        {note !== (event.ground_truth_note ?? "") && (
          <button
            type="button"
            disabled={pending}
            onClick={() => save({ ground_truth_note: note.trim() || null })}
            className="h-9 w-fit rounded-md bg-brand px-3 font-semibold text-white hover:bg-brand-strong"
          >
            Save note
          </button>
        )}
      </div>

      {state && (
        <p
          role={state.ok ? "status" : "alert"}
          className={state.ok ? "text-brand" : "text-critical"}
        >
          {state.message}
        </p>
      )}
    </div>
  );
}
