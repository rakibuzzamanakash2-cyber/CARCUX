"use client";

import { useActionState, useState } from "react";

import { login } from "@/app/actions/auth";
import { Field, FormMessage, SubmitButton } from "@/components/form";

export function LoginForm({ next }: { next?: string }) {
  const [state, action, pending] = useActionState(login, undefined);
  // Controlled, so React's automatic form reset after a failed attempt keeps it.
  // The password stays uncontrolled and is cleared on purpose.
  const [email, setEmail] = useState("");

  if (state?.challenge) {
    // Second step: the password was right; now the code from the authenticator app.
    return (
      <form action={action} className="flex flex-col gap-5 [&_label]:text-night-ink">
        <input type="hidden" name="next" value={next ?? "/"} />
        <input type="hidden" name="challenge" value={state.challenge} />
        <p className="text-sm text-night-ink">
          Open your authenticator app and enter the 6-digit code for CARCUX. Lost your phone? Enter
          one of your recovery codes instead.
        </p>
        <Field
          label="Code"
          name="code"
          type="text"
          inputMode="numeric"
          autoComplete="one-time-code"
          required
          autoFocus
          maxLength={20}
        />
        {state.message && <FormMessage state={state} />}
        <SubmitButton pending={pending} pendingText="Checking…">
          Sign in
        </SubmitButton>
      </form>
    );
  }

  return (
    <form action={action} className="flex flex-col gap-5 [&_label]:text-night-ink">
      <input type="hidden" name="next" value={next ?? "/"} />
      <Field
        label="Email"
        name="email"
        type="text"
        autoComplete="username"
        required
        autoFocus
        value={email}
        onChange={(e) => setEmail(e.target.value)}
      />
      <Field
        label="Password"
        name="password"
        type="password"
        autoComplete="current-password"
        required
      />
      <FormMessage state={state} />
      <SubmitButton pending={pending} pendingText="Signing in…">
        Sign in
      </SubmitButton>
    </form>
  );
}
