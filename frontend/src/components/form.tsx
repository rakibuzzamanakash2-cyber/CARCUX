"use client";

import { useId, type ComponentProps } from "react";

export function Field({
  label,
  hint,
  id,
  ...props
}: ComponentProps<"input"> & { label: string; hint?: string }) {
  // Explicit id/htmlFor so the accessible name is exactly the label; the hint is
  // announced separately as a description.
  const autoId = useId();
  const inputId = id ?? autoId;
  const hintId = `${inputId}-hint`;
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={inputId} className="text-sm font-semibold text-ink">
        {label}
      </label>
      <input
        {...props}
        id={inputId}
        aria-describedby={hint ? hintId : undefined}
        className="h-11 rounded-md border border-line bg-panel px-3 text-ink shadow-sm placeholder:text-muted/60 focus:border-brand focus:ring-2 focus:ring-brand/15 focus:outline-none"
      />
      {hint && (
        <span id={hintId} className="text-xs text-muted">
          {hint}
        </span>
      )}
    </div>
  );
}

export function TextAreaField({
  label,
  hint,
  ...props
}: ComponentProps<"textarea"> & { label: string; hint?: string }) {
  const id = useId();
  const hintId = `${id}-hint`;
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-semibold text-ink">
        {label}
      </label>
      <textarea
        {...props}
        id={id}
        aria-describedby={hint ? hintId : undefined}
        className="min-h-28 rounded-md border border-line bg-panel px-3 py-2.5 text-ink shadow-sm placeholder:text-muted/60 focus:border-brand focus:ring-2 focus:ring-brand/15 focus:outline-none"
      />
      {hint && (
        <span id={hintId} className="text-xs text-muted">
          {hint}
        </span>
      )}
    </div>
  );
}

export function SelectField({
  label,
  hint,
  children,
  ...props
}: ComponentProps<"select"> & { label: string; hint?: string }) {
  const id = useId();
  const hintId = `${id}-hint`;
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-semibold text-ink">
        {label}
      </label>
      <select
        {...props}
        id={id}
        aria-describedby={hint ? hintId : undefined}
        className="h-11 rounded-md border border-line bg-panel px-3 text-ink shadow-sm focus:border-brand focus:ring-2 focus:ring-brand/15 focus:outline-none"
      >
        {children}
      </select>
      {hint && (
        <span id={hintId} className="text-xs text-muted">
          {hint}
        </span>
      )}
    </div>
  );
}

export function SubmitButton({
  pending,
  children,
  pendingText,
}: {
  pending: boolean;
  children: React.ReactNode;
  pendingText: string;
}) {
  return (
    <button
      type="submit"
      disabled={pending}
      className="h-11 rounded-md bg-water px-5 font-semibold text-white transition-colors hover:bg-brand-strong disabled:cursor-wait disabled:opacity-60"
    >
      {pending ? pendingText : children}
    </button>
  );
}

export function FormMessage({ state }: { state: { ok: boolean; message: string } | undefined }) {
  if (!state) return null;
  return (
    <p
      role={state.ok ? "status" : "alert"}
      className={`rounded-md border px-3 py-2 text-sm text-ink ${
        state.ok ? "border-ok/50 bg-ok/10" : "border-critical/60 bg-critical-soft"
      }`}
    >
      {state.message}
    </p>
  );
}
