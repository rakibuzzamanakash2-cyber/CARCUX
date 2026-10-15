"use client";

import Link from "next/link";
import { startTransition, useActionState, useMemo, useState } from "react";

import { addLink, previewLink } from "@/app/actions/signals";
import { Field, FormMessage, SelectField, SubmitButton, TextAreaField } from "@/components/form";
import { EVENT_TYPE_GROUPS } from "@/lib/event-types";
import type { LinkPreview } from "@/lib/types";

const KINDS = [
  { value: "news", label: "News site" },
  { value: "public_record", label: "Official (government, UN, NGO)" },
  { value: "other", label: "Other website" },
];

export function LinkForm({
  districts,
  now,
  event,
}: {
  districts: { name: string; division: string }[];
  now: string;
  event: { id: string; title: string } | null;
}) {
  const [url, setUrl] = useState("");
  const [preview, setPreview] = useState<LinkPreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const [account, setAccount] = useState("");
  const [kind, setKind] = useState("news");
  const [body, setBody] = useState("");
  const [postedAt, setPostedAt] = useState(now);
  const [eventType, setEventType] = useState("");
  const [district, setDistrict] = useState("");
  const [relation, setRelation] = useState("supports");
  const [state, action, pending] = useActionState(addLink, undefined);

  const byDivision = useMemo(() => {
    const groups = new Map<string, string[]>();
    for (const d of districts) groups.set(d.division, [...(groups.get(d.division) ?? []), d.name]);
    return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [districts]);

  async function check(value: string) {
    if (!value.trim()) {
      setPreview(null);
      setPreviewError(null);
      return;
    }
    setChecking(true);
    const result = await previewLink(value);
    setChecking(false);
    if (result.ok) {
      setPreview(result.preview);
      setPreviewError(null);
      if (!account && result.preview.account) setAccount(result.preview.account);
    } else {
      setPreview(null);
      setPreviewError(result.message);
    }
  }

  function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    startTransition(() => action(new FormData(e.currentTarget)));
  }

  const web = preview?.platform === "web";
  const accountNeeded = preview !== null && !web && !preview.account;

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-5" aria-busy={pending}>
      <div className="flex flex-col gap-1.5">
        <Field
          label="Link"
          name="url"
          type="url"
          required
          placeholder="https://www.facebook.com/…"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onBlur={(e) => check(e.target.value)}
        />
        <p role="status" aria-live="polite" className="text-sm">
          {checking && <span className="text-muted">Reading the link…</span>}
          {previewError && <span className="text-critical">{previewError}</span>}
          {preview && !checking && (
            <span className="text-muted">
              <strong className="text-ink">{preview.platform_label}</strong>
              {preview.video ? " video" : preview.post_id ? " post" : " page"}
              {preview.account && ` by ${preview.account}`}
              {preview.known_source && ` · filed under ${preview.known_source}`}
            </span>
          )}
        </p>
        {preview?.existing_signal_id && (
          <p className="rounded-md bg-medium-soft px-3 py-2 text-sm">
            This post is already in CARCUX.{" "}
            <Link
              href={`/signals/${preview.existing_signal_id}`}
              className="font-semibold text-brand hover:underline"
            >
              Open it
            </Link>
            {event && " — or add it again below to link it to this event."}
          </p>
        )}
      </div>

      <div className="grid gap-5 sm:grid-cols-2">
        {web ? (
          <>
            <Field
              label="Publisher"
              name="account"
              placeholder={preview?.known_source ?? "e.g. The Business Standard"}
              value={account}
              onChange={(e) => setAccount(e.target.value)}
            />
            {!preview?.known_source && (
              <SelectField
                label="Kind of website"
                name="kind"
                value={kind}
                onChange={(e) => setKind(e.target.value)}
              >
                {KINDS.map((k) => (
                  <option key={k.value} value={k.value}>
                    {k.label}
                  </option>
                ))}
              </SelectField>
            )}
          </>
        ) : (
          <Field
            label={preview ? `${preview.platform_label} page, account or channel` : "Posted by"}
            name="account"
            required={accountNeeded}
            placeholder="e.g. Dhaka Updates"
            value={account}
            onChange={(e) => setAccount(e.target.value)}
          />
        )}
        <Field
          label="Posted at (Dhaka time)"
          name="published_at"
          type="datetime-local"
          required
          value={postedAt}
          onChange={(e) => setPostedAt(e.target.value)}
        />
      </div>

      <TextAreaField
        label="What it says"
        name="text"
        required
        rows={5}
        maxLength={4000}
        placeholder="Paste the post's text. For a video, write what is said or shown."
        value={body}
        onChange={(e) => setBody(e.target.value)}
      />

      <div className="grid gap-5 sm:grid-cols-2">
        <SelectField
          label="What it is about (optional)"
          name="event_type"
          value={eventType}
          onChange={(e) => setEventType(e.target.value)}
        >
          <option value="">Not sure</option>
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
          label="District (optional)"
          name="district"
          value={district}
          onChange={(e) => setDistrict(e.target.value)}
        >
          <option value="">Not stated</option>
          {byDivision.map(([division, names]) => (
            <optgroup key={division} label={division}>
              {names.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </optgroup>
          ))}
        </SelectField>
      </div>

      {event && (
        <fieldset className="rounded-lg border border-line p-3">
          <legend className="px-1 text-sm font-semibold">Link to “{event.title}” as</legend>
          <input type="hidden" name="event_id" value={event.id} />
          <div className="mt-1 flex flex-wrap gap-4 text-sm">
            {[
              ["supports", "Supports"],
              ["contradicts", "Contradicts"],
              ["related", "Related only"],
            ].map(([value, label]) => (
              <label key={value} className="flex items-center gap-2">
                <input
                  type="radio"
                  name="relation"
                  value={value}
                  checked={relation === value}
                  onChange={() => setRelation(value)}
                />
                {label}
              </label>
            ))}
          </div>
        </fieldset>
      )}

      <FormMessage state={state} />
      <SubmitButton pending={pending} pendingText="Adding…">
        {event ? "Add and link" : "Add the link"}
      </SubmitButton>
    </form>
  );
}
