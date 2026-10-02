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
      <label htmlFor={inputId} className="text-sm text-bone">
        {label}
      </label>
      <input
        {...props}
        id={inputId}
        aria-describedby={hint ? hintId : undefined}
        className="h-11 rounded-sm border border-line bg-panel-2 px-3 text-bone placeholder:text-steel/60 focus:border-steel focus:outline-none"
      />
      {hint && (
        <span id={hintId} className="text-xs text-steel">
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
      <label htmlFor={id} className="text-sm text-bone">
        {label}
      </label>
      <textarea
        {...props}
        id={id}
        aria-describedby={hint ? hintId : undefined}
        className="min-h-28 rounded-sm border border-line bg-panel-2 px-3 py-2.5 text-bone placeholder:text-steel/60 focus:border-steel focus:outline-none"
      />
      {hint && (
        <span id={hintId} className="text-xs text-steel">
          {hint}
        </span>
      )}
    </div>
  );
}

export function SelectField({
  label,
  children,
  ...props
}: ComponentProps<"select"> & { label: string }) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm text-bone">
        {label}
      </label>
      <select
        {...props}
        id={id}
        className="h-11 rounded-sm border border-line bg-panel-2 px-3 text-bone focus:border-steel focus:outline-none"
      >
        {children}
      </select>
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
      className="h-11 rounded-sm bg-bone px-5 font-semibold text-ground transition-colors hover:bg-white disabled:cursor-wait disabled:opacity-60"
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
      className={`border-l-2 pl-3 text-sm ${state.ok ? "border-ok text-bone" : "border-signal text-bone"}`}
    >
      {state.message}
    </p>
  );
}
