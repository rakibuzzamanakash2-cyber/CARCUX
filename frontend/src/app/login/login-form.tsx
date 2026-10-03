"use client";

import { useActionState, useState } from "react";

import { login } from "@/app/actions/auth";
import { Field, FormMessage, SubmitButton } from "@/components/form";

export function LoginForm({ next }: { next?: string }) {
  const [state, action, pending] = useActionState(login, undefined);
  // Controlled, so React's automatic form reset after a failed attempt keeps it.
  // The password stays uncontrolled and is cleared on purpose.
  const [email, setEmail] = useState("");

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
