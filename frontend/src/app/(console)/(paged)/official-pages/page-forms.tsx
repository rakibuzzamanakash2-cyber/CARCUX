"use client";

import { useActionState, useState, useTransition } from "react";

import {
  addOfficial,
  createPage,
  reinstatePage,
  suspendPage,
  updatePage,
  uploadLetter,
  verifyPage,
} from "@/app/actions/official";
import { Field, FormMessage, SelectField, SubmitButton, TextAreaField } from "@/components/form";
import { PAGE_KINDS, type ActionState, type OfficialPageDetail } from "@/lib/types";

function PageFields({ page }: { page?: OfficialPageDetail }) {
  return (
    <>
      <Field
        label="Name (English)"
        name="name"
        required
        minLength={3}
        maxLength={200}
        defaultValue={page?.name}
        placeholder="e.g. Ministry of Disaster Management and Relief"
      />
      <Field
        label="Name (Bangla, optional)"
        name="name_bn"
        maxLength={200}
        defaultValue={page?.name_bn ?? ""}
        placeholder="দুর্যোগ ব্যবস্থাপনা ও ত্রাণ মন্ত্রণালয়"
      />
      <SelectField label="What it is" name="kind" required defaultValue={page?.kind ?? ""}>
        <option value="">Choose</option>
        {PAGE_KINDS.map((k) => (
          <option key={k.value} value={k.value}>
            {k.label}
          </option>
        ))}
      </SelectField>
      <Field
        label="Official website (optional)"
        name="website"
        type="url"
        defaultValue={page?.website ?? ""}
        placeholder="https://modmr.gov.bd"
      />
      <Field
        label="Official email address"
        name="contact_email"
        type="email"
        defaultValue={page?.contact_email ?? ""}
        placeholder="info@modmr.gov.bd"
        hint="The office's own address (ideally .gov.bd). Needed to verify by email."
      />
      <div className="sm:col-span-2">
        <TextAreaField
          label="About (optional)"
          name="description"
          maxLength={2000}
          rows={3}
          defaultValue={page?.description ?? ""}
        />
      </div>
    </>
  );
}

export function CreatePageForm() {
  const [state, action, pending] = useActionState(createPage, undefined);
  return (
    <form action={action} className="grid max-w-3xl gap-5 sm:grid-cols-2">
      <Field
        label="Page address"
        name="slug"
        required
        minLength={3}
        maxLength={60}
        pattern="[a-z0-9]+(-[a-z0-9]+)*"
        placeholder="modmr"
        hint="Lowercase letters, digits and dashes. Shown as /official-pages/modmr."
      />
      <PageFields />
      <div className="flex flex-col gap-4 sm:col-span-2 sm:flex-row sm:items-center">
        <SubmitButton pending={pending} pendingText="Creating…">
          Create page (not verified yet)
        </SubmitButton>
        <FormMessage state={state} />
      </div>
    </form>
  );
}

export function EditPageForm({ page }: { page: OfficialPageDetail }) {
  const [state, action, pending] = useActionState(
    updatePage.bind(null, page.id, page.slug),
    undefined,
  );
  return (
    <form action={action} className="grid gap-5 sm:grid-cols-2">
      <PageFields page={page} />
      <div className="flex flex-col gap-4 sm:col-span-2 sm:flex-row sm:items-center">
        <SubmitButton pending={pending} pendingText="Saving…">
          Save details
        </SubmitButton>
        <FormMessage state={state} />
      </div>
    </form>
  );
}

export function LetterForm({ page }: { page: OfficialPageDetail }) {
  const [state, action, pending] = useActionState(
    uploadLetter.bind(null, page.id, page.slug),
    undefined,
  );
  return (
    <form action={action} className="flex flex-col gap-3">
      <Field
        label={page.has_document ? "Replace the letter" : "Scan of the official letter"}
        name="file"
        type="file"
        accept="application/pdf,image/jpeg,image/png"
        required
        hint="PDF, JPEG or PNG, up to 10 MB. Only admins can open it."
      />
      <div className="flex flex-wrap items-center gap-3">
        <SubmitButton pending={pending} pendingText="Uploading…">
          Upload letter
        </SubmitButton>
        <FormMessage state={state} />
      </div>
    </form>
  );
}

export function VerifyForm({ page }: { page: OfficialPageDetail }) {
  const [state, action, pending] = useActionState(
    verifyPage.bind(null, page.id, page.slug),
    undefined,
  );
  const [method, setMethod] = useState(page.has_document ? "official_letter" : "official_email");
  return (
    <form action={action} className="flex flex-col gap-3">
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-sm font-semibold">How did the office confirm it?</legend>
        <label className="flex items-start gap-2 text-sm">
          <input
            type="radio"
            name="method"
            value="official_email"
            checked={method === "official_email"}
            onChange={() => setMethod("official_email")}
            className="mt-1"
          />
          <span>
            By email from its own address
            <span className="block text-muted">
              {page.contact_email ?? "Add the official email address under Details first."}
            </span>
          </span>
        </label>
        <label className="flex items-start gap-2 text-sm">
          <input
            type="radio"
            name="method"
            value="official_letter"
            checked={method === "official_letter"}
            onChange={() => setMethod("official_letter")}
            className="mt-1"
          />
          <span>
            By official letter
            <span className="block text-muted">
              {page.has_document ? "Letter on file." : "Upload the letter first."}
            </span>
          </span>
        </label>
      </fieldset>
      <TextAreaField
        label="What you checked"
        name="note"
        required
        minLength={10}
        maxLength={2000}
        rows={3}
        placeholder="Who confirmed, from which address or with which letter reference, and when."
      />
      <div className="flex flex-wrap items-center gap-3">
        <SubmitButton pending={pending} pendingText="Verifying…">
          Verify page
        </SubmitButton>
        <FormMessage state={state} />
      </div>
    </form>
  );
}

export function SuspendForm({ page }: { page: OfficialPageDetail }) {
  const [state, action, pending] = useActionState(
    suspendPage.bind(null, page.id, page.slug),
    undefined,
  );
  return (
    <form action={action} className="flex flex-col gap-3">
      <TextAreaField
        label="Reason for suspending"
        name="reason"
        required
        minLength={10}
        maxLength={2000}
        rows={2}
        hint="The page is hidden and cannot publish until it is reinstated."
      />
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="submit"
          disabled={pending}
          className="h-11 rounded-md border border-critical px-5 font-semibold text-critical hover:bg-critical-soft disabled:opacity-60"
        >
          {pending ? "Suspending…" : "Suspend page"}
        </button>
        <FormMessage state={state} />
      </div>
    </form>
  );
}

export function ReinstateButton({ page }: { page: OfficialPageDetail }) {
  const [pending, startTransition] = useTransition();
  const [state, setState] = useState<ActionState>();
  return (
    <div className="flex flex-wrap items-center gap-3">
      <button
        type="button"
        disabled={pending}
        onClick={() =>
          startTransition(async () => setState(await reinstatePage(page.id, page.slug)))
        }
        className="h-11 rounded-md bg-water px-5 font-semibold text-white hover:bg-brand-strong disabled:opacity-60"
      >
        {pending ? "Reinstating…" : "Reinstate page"}
      </button>
      <FormMessage state={state} />
    </div>
  );
}

export function AddOfficialForm({ page }: { page: OfficialPageDetail }) {
  const [state, action, pending] = useActionState(async (prev: ActionState, formData: FormData) => {
    const result = await addOfficial(page.id, page.slug, prev, formData);
    return result;
  }, undefined);
  return (
    <form action={action} className="grid gap-4 sm:grid-cols-3">
      <Field label="Full name" name="full_name" required maxLength={200} />
      <Field
        label="Email"
        name="email"
        type="email"
        required
        placeholder="name@modmr.gov.bd"
        hint="Their work address at the office."
      />
      <Field
        label="Temporary password"
        name="password"
        type="password"
        required
        minLength={12}
        autoComplete="new-password"
        hint="At least 12 characters. Share it privately."
      />
      <div className="flex flex-col gap-3 sm:col-span-3 sm:flex-row sm:items-center">
        <SubmitButton pending={pending} pendingText="Creating…">
          Add official account
        </SubmitButton>
        <FormMessage state={state} />
      </div>
    </form>
  );
}
