"use client";

import { startTransition, useActionState, useMemo, useState } from "react";

import { enterBulletin } from "@/app/actions/signals";
import { Field, FormMessage, SelectField, SubmitButton, TextAreaField } from "@/components/form";
import { EVENT_TYPE_GROUPS } from "@/lib/event-types";
import { SEVERITIES } from "@/lib/signals";

export function BulletinForm({
  sources,
  districts,
  now,
}: {
  sources: { id: string; name: string }[];
  districts: { name: string; division: string }[];
  now: string;
}) {
  // Controlled fields: nothing typed is lost if the server refuses the form.
  const [sourceId, setSourceId] = useState(sources[0]?.id ?? "");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [url, setUrl] = useState("");
  const [eventType, setEventType] = useState("");
  const [severity, setSeverity] = useState("");
  const [publishedAt, setPublishedAt] = useState(now);
  const [validUntil, setValidUntil] = useState("");
  const [district, setDistrict] = useState("");
  const [placeName, setPlaceName] = useState("");
  const [language, setLanguage] = useState("en");
  const [state, action, pending] = useActionState(enterBulletin, undefined);

  const byDivision = useMemo(() => {
    const groups = new Map<string, string[]>();
    for (const d of districts) groups.set(d.division, [...(groups.get(d.division) ?? []), d.name]);
    return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [districts]);

  function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    startTransition(() => action(new FormData(event.currentTarget)));
  }

  if (sources.length === 0) {
    return (
      <p className="text-muted">
        No source is set up for bulletins entered by hand. An admin can switch one on under Sources.
      </p>
    );
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-5" aria-busy={pending}>
      <div className="grid gap-5 sm:grid-cols-2">
        <SelectField
          label="Issued by"
          name="source_id"
          required
          value={sourceId}
          onChange={(e) => setSourceId(e.target.value)}
        >
          {sources.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </SelectField>
        <Field
          label="Issued at (Dhaka time)"
          name="published_at"
          type="datetime-local"
          required
          value={publishedAt}
          onChange={(e) => setPublishedAt(e.target.value)}
        />
      </div>
      <Field
        label="Headline"
        name="title"
        required
        minLength={5}
        maxLength={400}
        placeholder="e.g. Special Weather Bulletin No. 4: danger signal 7 for Chattogram port"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
      />
      <TextAreaField
        label="Key text"
        name="text"
        rows={5}
        maxLength={4000}
        hint="The lines that matter: areas, levels, times, advice."
        value={body}
        onChange={(e) => setBody(e.target.value)}
      />
      <Field
        label="Link to the original"
        name="url"
        type="url"
        maxLength={1000}
        placeholder="https://"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
      />
      <div className="grid gap-5 sm:grid-cols-2">
        <SelectField
          label="About"
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
          label="Severity"
          name="severity"
          value={severity}
          onChange={(e) => setSeverity(e.target.value)}
          hint={SEVERITIES.find((s) => s.value === severity)?.meaning ?? "Optional."}
        >
          <option value="">Not rated</option>
          {SEVERITIES.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </SelectField>
      </div>
      <div className="grid gap-5 sm:grid-cols-2">
        <SelectField
          label="District it concerns most"
          name="district"
          required
          value={district}
          onChange={(e) => setDistrict(e.target.value)}
          hint="Placed at the district centre; it will match events across the district."
        >
          <option value="">Choose a district</option>
          {byDivision.map(([division, names]) => (
            <optgroup key={division} label={`${division} division`}>
              {names.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </optgroup>
          ))}
        </SelectField>
        <Field
          label="Place name"
          name="place_name"
          maxLength={200}
          placeholder="Optional, e.g. Chattogram port"
          value={placeName}
          onChange={(e) => setPlaceName(e.target.value)}
        />
      </div>
      <div className="grid gap-5 sm:grid-cols-2">
        <Field
          label="In effect until (Dhaka time)"
          name="valid_until"
          type="datetime-local"
          hint="Optional. When the warning or forecast ends."
          value={validUntil}
          onChange={(e) => setValidUntil(e.target.value)}
        />
        <SelectField
          label="Language"
          name="language"
          value={language}
          onChange={(e) => setLanguage(e.target.value)}
        >
          <option value="en">English</option>
          <option value="bn">Bangla</option>
          <option value="mixed">Mixed</option>
        </SelectField>
      </div>
      <div className="flex flex-col gap-4 border-t border-line pt-5 sm:flex-row sm:items-center">
        <SubmitButton pending={pending} pendingText="Saving…">
          Save bulletin
        </SubmitButton>
        <FormMessage state={state} />
      </div>
    </form>
  );
}
