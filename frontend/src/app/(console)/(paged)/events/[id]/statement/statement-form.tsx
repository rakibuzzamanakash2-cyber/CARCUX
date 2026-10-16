"use client";

import { useActionState, useState } from "react";

import { publishStatement } from "@/app/actions/statements";
import { Field, FormMessage, SubmitButton, TextAreaField } from "@/components/form";
import { FINDINGS, type Statement } from "@/lib/types";

export function StatementForm({
  eventId,
  correcting,
}: {
  eventId: string;
  correcting: Statement | null;
}) {
  const [state, action, pending] = useActionState(publishStatement.bind(null, eventId), undefined);
  const [finding, setFinding] = useState(correcting?.finding ?? "");
  return (
    <form action={action} className="flex flex-col gap-5">
      {correcting && (
        <div className="rounded-md border border-alert/50 bg-alert-soft/50 p-3 text-sm">
          <input type="hidden" name="supersedes_id" value={correcting.id} />
          This corrects your page&apos;s earlier statement, “{correcting.title}”. Both stay public;
          the earlier one is marked as corrected.
        </div>
      )}
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-sm font-semibold">Your finding</legend>
        {FINDINGS.map((f) => (
          <label key={f.value} className="flex items-start gap-2 text-sm">
            <input
              type="radio"
              name="finding"
              value={f.value}
              required
              checked={finding === f.value}
              onChange={() => setFinding(f.value)}
              className="mt-1"
            />
            <span>
              <span className="font-semibold">{f.label}</span>
              <span className="text-muted"> · {f.description}</span>
            </span>
          </label>
        ))}
      </fieldset>
      <Field label="Title" name="title" required minLength={5} maxLength={200} />
      <TextAreaField
        label="Statement"
        name="body"
        required
        minLength={20}
        maxLength={5000}
        rows={9}
        hint="In your own words: what happened, what is being done, what people should do. Published as written and cannot be edited; a correction is a new statement."
      />
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <SubmitButton pending={pending} pendingText="Publishing…">
          {correcting ? "Publish correction" : "Publish statement"}
        </SubmitButton>
        <FormMessage state={state} />
      </div>
    </form>
  );
}
