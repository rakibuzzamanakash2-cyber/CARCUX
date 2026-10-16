"use client";

import Link from "next/link";
import { useState, useTransition } from "react";

import { updateEvent } from "@/app/actions/events";
import { PriorityBadge } from "@/components/event-badges";
import { FormMessage } from "@/components/form";
import { priorityLabel } from "@/lib/events";
import type { ActionState, Briefing, CarcuxEvent, CitedSentence } from "@/lib/types";

/** The suggested priority, the reason for each point, and a button to take it. */
export function PrioritySuggestionPanel({
  event,
  briefing,
}: {
  event: CarcuxEvent;
  briefing: Briefing;
}) {
  const [pending, startTransition] = useTransition();
  const [result, setResult] = useState<ActionState>();
  const p = briefing.priority;
  return (
    <div
      className="flex flex-col gap-3 text-sm"
      aria-busy={pending}
      data-testid="priority-suggestion"
    >
      <div className="flex items-center justify-between gap-2">
        <PriorityBadge priority={p.level} />
        <span className="text-muted">{p.score} points</span>
      </div>
      <ul className="flex flex-col gap-1">
        {p.factors.map((f) => (
          <li key={f.name} className="flex gap-2">
            <span
              className={`w-8 shrink-0 text-right font-semibold tabular-nums ${f.points < 0 ? "text-ok" : f.points > 0 ? "text-ink" : "text-muted"}`}
            >
              {f.points > 0 ? `+${f.points}` : f.points}
            </span>
            <span>{f.reason}</span>
          </li>
        ))}
      </ul>
      {event.priority === p.level ? (
        <p className="text-muted">This is the current priority.</p>
      ) : (
        <button
          type="button"
          disabled={pending}
          onClick={() =>
            startTransition(async () =>
              setResult(await updateEvent(event.id, { priority: p.level })),
            )
          }
          className="h-10 w-fit rounded-md border border-brand px-4 font-semibold text-brand hover:bg-brand-soft disabled:opacity-60"
        >
          {pending ? "Saving…" : `Set to ${priorityLabel(p.level).toLowerCase()}`}
        </button>
      )}
      <FormMessage state={result} />
      <p className="text-xs text-muted">
        From what can hurt people or stop movement, how many, whether it is growing, how long it has
        lasted and how sure we are; never from who is involved. Critical from 8 points, high from 5,
        medium from 3. A suggestion only: the history records whether it was followed.
      </p>
    </div>
  );
}

/** Sentences with numbered citations; each number opens the item it rests on. */
function Cited({
  sentences,
  number,
  base,
  labels,
}: {
  sentences: CitedSentence[];
  number: Map<string, number>;
  base: string;
  labels: Map<string, string>;
}) {
  return (
    <ul className="flex flex-col gap-2">
      {sentences.map((s, i) => (
        <li
          key={i}
          data-kind={s.kind}
          className={s.kind === "disputed" || s.kind === "denial" ? "text-alert" : ""}
        >
          <span className="text-ink">{s.text}</span>
          {s.cites.map((id) => (
            <Link
              key={id}
              href={`${base}?tab=evidence#evidence-${id}`}
              title={labels.get(id) ?? "Linked item"}
              className="ml-1 inline-block rounded bg-brand-soft px-1.5 text-xs font-semibold text-brand hover:underline"
            >
              {number.get(id) ?? "?"}
            </Link>
          ))}
        </li>
      ))}
    </ul>
  );
}

const WINDOWS = [
  { hours: 1, label: "1 hour" },
  { hours: 6, label: "6 hours" },
  { hours: 24, label: "24 hours" },
  { hours: 168, label: "7 days" },
];

/** CARCUX's summary of the evidence and what changed: every sentence cites items. */
export function BriefingPanel({
  briefing,
  base,
  order,
  labels,
  hours,
}: {
  briefing: Briefing;
  base: string;
  order: string[]; // evidence link ids, in the Evidence tab's order
  labels: Map<string, string>;
  hours: number;
}) {
  const number = new Map(order.map((id, i) => [id, i + 1]));
  return (
    <div className="flex flex-col gap-5 text-[15px]" data-testid="briefing">
      <Cited sentences={briefing.summary} number={number} base={base} labels={labels} />
      <div>
        <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1">
          <h3 className="font-semibold">What changed in the last</h3>
          <nav aria-label="Period" className="flex gap-1 text-sm">
            {WINDOWS.map((w) => (
              <Link
                key={w.hours}
                href={`${base}?changes=${w.hours}#briefing`}
                aria-current={w.hours === hours ? "page" : undefined}
                className={`rounded px-2 py-0.5 ${w.hours === hours ? "bg-brand text-white" : "text-brand hover:bg-brand-soft"}`}
              >
                {w.label}
              </Link>
            ))}
          </nav>
        </div>
        <Cited sentences={briefing.changes} number={number} base={base} labels={labels} />
      </div>
      <p className="text-xs text-muted">
        Written by CARCUX from the linked evidence, not by a person. The numbers are the items each
        sentence rests on, in the order of the Evidence tab; field workers are never named.
      </p>
    </div>
  );
}
