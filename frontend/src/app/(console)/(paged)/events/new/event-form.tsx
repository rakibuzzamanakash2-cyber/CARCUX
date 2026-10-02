"use client";

import { startTransition, useActionState, useState } from "react";

import { createEvent } from "@/app/actions/events";
import { Field, FormMessage, SelectField, SubmitButton, TextAreaField } from "@/components/form";
import { EVENT_TYPE_GROUPS } from "@/lib/event-types";
import { PRIORITIES } from "@/lib/events";

export interface EventDraft {
  title: string;
  event_type: string;
  place_name: string;
  latitude: string;
  longitude: string;
  started_at: string;
  report: { id: string; text: string; reporter: string } | null;
}

export function EventForm({ draft }: { draft: EventDraft }) {
  // Controlled fields: nothing typed is lost if the server refuses the form.
  const [title, setTitle] = useState(draft.title);
  const [eventType, setEventType] = useState(draft.event_type);
  const [placeName, setPlaceName] = useState(draft.place_name);
  const [latitude, setLatitude] = useState(draft.latitude);
  const [longitude, setLongitude] = useState(draft.longitude);
  const [startedAt, setStartedAt] = useState(draft.started_at);
  const [priority, setPriority] = useState("medium");
  const [summary, setSummary] = useState("");
  const [state, action, pending] = useActionState(createEvent, undefined);

  function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    startTransition(() => action(new FormData(event.currentTarget)));
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-5" aria-busy={pending}>
      {draft.report && (
        <div className="rounded-md border border-ok/50 bg-ok/10 px-3 py-2 text-sm">
          <p className="text-steel">
            Starting from a report by {draft.report.reporter}. It will be attached as supporting
            evidence.
          </p>
          <p className="line-clamp-2">{draft.report.text}</p>
          <input type="hidden" name="field_report_ids" value={draft.report.id} />
        </div>
      )}
      <Field
        label="Title"
        name="title"
        required
        minLength={5}
        maxLength={160}
        placeholder="e.g. Waterlogging at Mirpur 10 circle"
        hint="Neutral and factual: what, and where. No names of private individuals."
        value={title}
        onChange={(e) => setTitle(e.target.value)}
      />
      <div className="grid gap-5 sm:grid-cols-2">
        <SelectField
          label="Type of event"
          name="event_type"
          required
          value={eventType}
          onChange={(e) => setEventType(e.target.value)}
        >
          <option value="">Choose a type</option>
          {EVENT_TYPE_GROUPS.map((g) => (
            <optgroup key={g.family} label={g.family}>
              {g.types.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </optgroup>
          ))}
        </SelectField>
        <SelectField
          label="Priority"
          name="priority"
          value={priority}
          onChange={(e) => setPriority(e.target.value)}
        >
          {PRIORITIES.map((p) => (
            <option key={p.value} value={p.value}>
              {p.label}
            </option>
          ))}
        </SelectField>
      </div>
      <Field
        label="Place name"
        name="place_name"
        maxLength={200}
        placeholder="e.g. Mirpur 10 golchottor"
        value={placeName}
        onChange={(e) => setPlaceName(e.target.value)}
      />
      <div className="grid gap-5 sm:grid-cols-3">
        <Field
          label="Latitude"
          name="latitude"
          required
          inputMode="decimal"
          placeholder="23.8069"
          value={latitude}
          onChange={(e) => setLatitude(e.target.value)}
        />
        <Field
          label="Longitude"
          name="longitude"
          required
          inputMode="decimal"
          placeholder="90.3687"
          value={longitude}
          onChange={(e) => setLongitude(e.target.value)}
        />
        <Field
          label="Started (Dhaka time)"
          name="started_at"
          type="datetime-local"
          required
          value={startedAt}
          onChange={(e) => setStartedAt(e.target.value)}
        />
      </div>
      <TextAreaField
        label="Summary"
        name="summary"
        maxLength={4000}
        rows={3}
        hint="Optional. What is known so far, and what is not."
        value={summary}
        onChange={(e) => setSummary(e.target.value)}
      />
      <div className="flex flex-col gap-4 border-t border-line pt-5 sm:flex-row sm:items-center">
        <SubmitButton pending={pending} pendingText="Creating…">
          Create event
        </SubmitButton>
        <FormMessage state={state} />
      </div>
    </form>
  );
}
