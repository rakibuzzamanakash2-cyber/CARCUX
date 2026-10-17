"use client";

import { ArrowDown, ArrowUp, Send } from "lucide-react";
import Link from "next/link";
import { useActionState, useState, useTransition } from "react";

import { closeRequest, requestEvidence } from "@/app/actions/evidence-requests";
import { FormMessage, SubmitButton, TextAreaField } from "@/components/form";
import { eventTypeLabel } from "@/lib/event-types";
import { formatDhaka, percent } from "@/lib/format";
import type { ActionState, CarcuxEvent, CheckValue, EvidenceRequest } from "@/lib/types";

/** A question in neutral words: it names the place and kind of event, not what anyone
 * believes, and asks for a report either way. */
function neutralQuestion(event: CarcuxEvent): string {
  const what = eventTypeLabel(event.event_type).toLowerCase();
  const where = event.place_name ?? "the place marked on the map";
  return `Is there ${what} at ${where} now? Say what you see, even if nothing is happening.`;
}

function WhatACheckWouldDo({ value }: { value: CheckValue }) {
  if (value.probability === null) {
    return (
      <p className="text-sm text-muted">
        No evidence yet. One field report would move it to {percent(value.if_supported)} if it says
        it is happening, or {percent(value.if_denied)} if it says it is not.
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-2 text-sm">
      <p className="text-muted">
        One more field report would move it from {percent(value.probability)}:
      </p>
      <ul className="flex flex-col gap-1">
        <li className="inline-flex items-center gap-2">
          <ArrowUp size={15} aria-hidden="true" className="text-ok" />
          to <strong>{percent(value.if_supported)}</strong> if it says it is happening
        </li>
        <li className="inline-flex items-center gap-2">
          <ArrowDown size={15} aria-hidden="true" className="text-critical" />
          to <strong>{percent(value.if_denied)}</strong> if it says it is not
        </li>
      </ul>
      <p>
        {value.changes >= 0.995
          ? "Either answer would change the assessment."
          : value.changes <= 0.005
            ? "One report alone would not change the assessment."
            : `A ${percent(value.changes)} chance that a check changes the assessment.`}
      </p>
    </div>
  );
}

function OpenRequest({ eventId, request }: { eventId: string; request: EvidenceRequest }) {
  const [pending, startTransition] = useTransition();
  const [result, setResult] = useState<ActionState>();
  const close = (status: "answered" | "cancelled") =>
    startTransition(async () => setResult(await closeRequest(eventId, request.id, status)));
  const n = request.responses.length;
  return (
    <div className="flex flex-col gap-3 rounded-md border border-water/40 bg-water/5 p-3 text-sm">
      <p className="font-semibold">Asked field workers to check</p>
      <p className="italic">“{request.question}”</p>
      <p className="text-muted">
        {request.created_by.full_name}, {formatDhaka(request.created_at)}.{" "}
        {n === 0 ? "No answers yet." : `${n} ${n === 1 ? "answer" : "answers"}:`}
      </p>
      {n > 0 && (
        <ul className="flex flex-col gap-1">
          {request.responses.map((r) => (
            <li key={r.id}>
              <Link href={`/field-reports/${r.id}`} className="text-brand hover:underline">
                {r.text.length > 90 ? `${r.text.slice(0, 87)}…` : r.text}
              </Link>{" "}
              <span className="text-muted">({formatDhaka(r.received_at)})</span>
            </li>
          ))}
        </ul>
      )}
      {n > 0 && (
        <p className="text-muted">
          Answers are ordinary reports: link each to the event from the Evidence tab as what it
          says.
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={pending}
          onClick={() => close("answered")}
          className="rounded-md bg-brand px-3 py-1.5 font-semibold text-white hover:bg-brand-strong disabled:opacity-60"
        >
          Close as answered
        </button>
        <button
          type="button"
          disabled={pending}
          onClick={() => close("cancelled")}
          className="rounded-md border border-line px-3 py-1.5 font-semibold hover:bg-panel-2 disabled:opacity-60"
        >
          Cancel request
        </button>
      </div>
      <FormMessage state={result} />
    </div>
  );
}

/** What one more field report would do, and asking field workers to go and check. */
export function CheckPanel({
  event,
  value,
  requests,
}: {
  event: CarcuxEvent;
  value: CheckValue | null;
  requests: EvidenceRequest[];
}) {
  const open = requests.find((r) => r.status === "open");
  const closed = requests.filter((r) => r.status !== "open");
  const canAsk = event.status === "active" || event.status === "monitoring";
  const [state, action, pending] = useActionState(requestEvidence.bind(null, event.id), undefined);

  return (
    <div className="flex flex-col gap-4">
      {value && <WhatACheckWouldDo value={value} />}
      {open ? (
        <OpenRequest eventId={event.id} request={open} />
      ) : canAsk ? (
        <form action={action} className="flex flex-col gap-3">
          <TextAreaField
            label="Ask field workers to check"
            name="question"
            rows={3}
            maxLength={500}
            required
            defaultValue={neutralQuestion(event)}
            hint="They see this question, the place and the kind of event, never the assessment, so they report what they see. Keep it neutral."
          />
          <FormMessage state={state} />
          <div>
            <SubmitButton pending={pending} pendingText="Sending…">
              <span className="inline-flex items-center gap-2">
                <Send size={16} aria-hidden="true" />
                Request more evidence
              </span>
            </SubmitButton>
          </div>
        </form>
      ) : (
        <p className="text-sm text-muted">The event is closed; reopen it to ask for a check.</p>
      )}
      {closed.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-muted">
            Earlier requests ({closed.length})
          </summary>
          <ul className="mt-2 flex flex-col gap-2">
            {closed.map((r) => (
              <li key={r.id}>
                “{r.question}”{" "}
                <span className="text-muted">
                  {r.status === "answered" ? "Answered" : "Cancelled"}
                  {r.closed_at ? ` ${formatDhaka(r.closed_at)}` : ""}, {r.responses.length}{" "}
                  {r.responses.length === 1 ? "answer" : "answers"}
                  {r.close_note ? `. ${r.close_note}` : ""}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
