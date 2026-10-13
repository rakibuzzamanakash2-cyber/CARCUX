"use client";

import { Download, Power } from "lucide-react";
import { startTransition, useActionState, useState, useTransition } from "react";

import { addFeed, fetchNow, setSourceEnabled } from "@/app/actions/signals";
import { Field, FormMessage, SelectField, SubmitButton } from "@/components/form";
import type { ActionState } from "@/lib/types";

const btn =
  "inline-flex h-9 items-center gap-1.5 rounded-lg border px-3 text-sm font-semibold shadow-sm transition-colors disabled:cursor-wait disabled:opacity-60";

/** Admin: read now, and switch on or off. */
export function SourceActions({
  sourceId,
  name,
  enabled,
  readable,
}: {
  sourceId: string;
  name: string;
  enabled: boolean;
  readable: boolean;
}) {
  const [pending, start] = useTransition();
  const [state, setState] = useState<ActionState>();
  return (
    <div className="flex min-w-48 flex-col items-end gap-1.5" aria-busy={pending}>
      <div className="flex flex-wrap justify-end gap-2">
        {readable && enabled && (
          <button
            type="button"
            disabled={pending}
            onClick={() => start(async () => setState(await fetchNow(sourceId)))}
            className={`${btn} border-brand bg-panel text-brand hover:bg-brand-soft`}
          >
            <Download size={15} aria-hidden="true" />
            {pending ? "Reading…" : "Read now"}
            <span className="sr-only"> {name}</span>
          </button>
        )}
        <button
          type="button"
          disabled={pending}
          aria-pressed={enabled}
          onClick={() => start(async () => setState(await setSourceEnabled(sourceId, !enabled)))}
          className={`${btn} ${
            enabled
              ? "border-line bg-panel text-ink hover:border-red hover:text-red"
              : "border-brand bg-brand text-white hover:bg-brand-strong"
          }`}
        >
          <Power size={15} aria-hidden="true" />
          {enabled ? "Switch off" : "Switch on"}
          <span className="sr-only"> {name}</span>
        </button>
      </div>
      {state && (
        <p
          role={state.ok ? "status" : "alert"}
          className={`max-w-72 text-right text-sm ${state.ok ? "text-brand" : "text-critical"}`}
        >
          {state.message}
        </p>
      )}
    </div>
  );
}

export function AddFeedForm() {
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [language, setLanguage] = useState("en");
  const [every, setEvery] = useState("30");
  const [state, action, pending] = useActionState(async (prev: ActionState, formData: FormData) => {
    const result = await addFeed(prev, formData);
    if (result?.ok) {
      setName("");
      setUrl("");
    }
    return result;
  }, undefined);

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        startTransition(() => action(new FormData(e.currentTarget)));
      }}
      className="flex flex-col gap-5"
      aria-busy={pending}
    >
      <div className="grid gap-5 sm:grid-cols-2">
        <Field
          label="Name"
          name="name"
          required
          minLength={2}
          maxLength={120}
          placeholder="e.g. Dhaka Tribune"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <Field
          label="Feed address"
          name="url"
          type="url"
          required
          maxLength={500}
          placeholder="https://…/rss.xml"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
      </div>
      <div className="grid gap-5 sm:grid-cols-2">
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
        <SelectField
          label="Read"
          name="interval_minutes"
          value={every}
          onChange={(e) => setEvery(e.target.value)}
        >
          <option value="15">Every 15 minutes</option>
          <option value="30">Every 30 minutes</option>
          <option value="60">Every hour</option>
          <option value="180">Every 3 hours</option>
        </SelectField>
      </div>
      <div className="flex flex-col gap-4 border-t border-line pt-5 sm:flex-row sm:items-center">
        <SubmitButton pending={pending} pendingText="Adding…">
          Add feed
        </SubmitButton>
        <FormMessage state={state} />
      </div>
    </form>
  );
}
