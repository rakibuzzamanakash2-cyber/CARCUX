"use client";

import { useActionState } from "react";

import { signIn } from "@/app/actions/public";
import { Field, FormMessage, SubmitButton } from "@/components/form";

export function SignInForm({ next }: { next: string }) {
  const [state, action, pending] = useActionState(signIn, undefined);
  return (
    <form
      action={action}
      className="flex flex-col gap-4 rounded-xl border border-line bg-panel p-5"
    >
      <input type="hidden" name="next" value={next} />
      <Field label="Email" name="email" type="email" required autoComplete="email" />
      <Field
        label="Password"
        name="password"
        type="password"
        required
        autoComplete="current-password"
      />
      <SubmitButton pending={pending} pendingText="Signing in…">
        Sign in
      </SubmitButton>
      <FormMessage state={state} />
    </form>
  );
}
