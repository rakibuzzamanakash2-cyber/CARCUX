"use client";

import { useId, useState, useTransition } from "react";

import { backfillSource } from "@/app/actions/signals";
import type { ActionState } from "@/lib/types";

/** Case studies with generous windows around them (check the dates against sources). */
const CASE_STUDIES = [
  { label: "Sylhet and Sunamganj floods, June 2022", start: "2022-06-10", end: "2022-07-05" },
  { label: "Cyclone Sitrang, October 2022", start: "2022-10-21", end: "2022-10-28" },
  { label: "Cyclone Mocha, May 2023", start: "2023-05-09", end: "2023-05-18" },
  { label: "Chattogram and Bandarban floods, August 2023", start: "2023-08-02", end: "2023-08-15" },
  { label: "Cyclone Remal, May 2024", start: "2024-05-22", end: "2024-05-31" },
  {
    label: "Feni, Noakhali and Cumilla floods, August 2024",
    start: "2024-08-18",
    end: "2024-09-15",
  },
  { label: "Narsingdi earthquake, November 2025", start: "2025-11-15", end: "2025-11-30" },
];

const inputCls =
  "h-10 w-full rounded-md border border-line bg-panel px-3 text-ink shadow-sm focus:border-brand focus:outline-none";

export function BackfillForm({ sources }: { sources: { id: string; name: string }[] }) {
  const ids = useId();
  const [pending, startTransition] = useTransition();
  const [state, setState] = useState<ActionState>();
  const [sourceId, setSourceId] = useState(sources[0]?.id ?? "");
  const [preset, setPreset] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");

  return (
    <form
      className="flex flex-col gap-4 text-sm"
      aria-busy={pending}
      onSubmit={(e) => {
        e.preventDefault();
        setState(undefined);
        startTransition(async () => setState(await backfillSource(sourceId, start, end)));
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <label htmlFor={`${ids}-case`} className="font-semibold">
            Case study
          </label>
          <select
            id={`${ids}-case`}
            value={preset}
            onChange={(e) => {
              setPreset(e.target.value);
              const c = CASE_STUDIES.find((x) => x.label === e.target.value);
              if (c) {
                setStart(c.start);
                setEnd(c.end);
              }
            }}
            className={inputCls}
          >
            <option value="">Choose, or set the dates yourself</option>
            {CASE_STUDIES.map((c) => (
              <option key={c.label} value={c.label}>
                {c.label}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor={`${ids}-src`} className="font-semibold">
            Archive
          </label>
          <select
            id={`${ids}-src`}
            value={sourceId}
            onChange={(e) => setSourceId(e.target.value)}
            className={inputCls}
          >
            {sources.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor={`${ids}-from`} className="font-semibold">
            From
          </label>
          <input
            id={`${ids}-from`}
            type="date"
            required
            value={start}
            onChange={(e) => setStart(e.target.value)}
            className={inputCls}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor={`${ids}-to`} className="font-semibold">
            To
          </label>
          <input
            id={`${ids}-to`}
            type="date"
            required
            value={end}
            onChange={(e) => setEnd(e.target.value)}
            className={inputCls}
          />
        </div>
      </div>
      <div className="flex flex-col gap-3 border-t border-line pt-4 sm:flex-row sm:items-center">
        <button
          type="submit"
          disabled={pending || !sourceId}
          className="h-10 rounded-lg bg-brand px-5 font-semibold text-white hover:bg-brand-strong disabled:cursor-wait disabled:opacity-60"
        >
          {pending ? "Reading the archive…" : "Fill in this period"}
        </button>
        {state && (
          <p
            role={state.ok ? "status" : "alert"}
            className={state.ok ? "text-brand" : "text-critical"}
          >
            {state.message}
          </p>
        )}
      </div>
    </form>
  );
}
