"use client";

import { useActionState } from "react";

import { changePassword } from "@/app/actions/review";
import { Field, FormMessage, SubmitButton } from "@/components/form";

export function PasswordForm() {
  const [state, action, pending] = useActionState(changePassword, undefined);
  // Uncontrolled on purpose: React clears password fields after every attempt.
  return (
    <form action={action} className="flex max-w-md flex-col gap-4">
      <Field
        label="Current password"
        name="current_password"
        type="password"
        autoComplete="current-password"
        required
      />
      <Field
        label="New password"
        name="new_password"
        type="password"
        autoComplete="new-password"
        minLength={12}
        required
      />
      <Field
        label="New password again"
        name="confirm_password"
        type="password"
        autoComplete="new-password"
        minLength={12}
        required
      />
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <SubmitButton pending={pending} pendingText="Changing…">
          Change password
        </SubmitButton>
        <FormMessage state={state} />
      </div>
    </form>
  );
}
