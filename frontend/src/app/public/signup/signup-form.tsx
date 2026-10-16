"use client";

import Link from "next/link";
import { useActionState } from "react";

import { signUp } from "@/app/actions/public";
import { Field, FormMessage, SubmitButton } from "@/components/form";

export function SignUpForm() {
  const [state, action, pending] = useActionState(signUp, undefined);
  if (state?.ok) return <FormMessage state={state} />;
  return (
    <form
      action={action}
      className="flex flex-col gap-4 rounded-xl border border-line bg-panel p-5"
    >
      <Field
        label="Name shown with your comments"
        name="display_name"
        required
        minLength={2}
        maxLength={50}
        autoComplete="nickname"
      />
      <Field label="Email" name="email" type="email" required autoComplete="email" />
      <Field
        label="Password"
        name="password"
        type="password"
        required
        minLength={10}
        autoComplete="new-password"
        hint="10 characters or more."
      />
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" name="agree" required className="mt-1" />
        <span>
          I agree to the{" "}
          <Link
            href="/public/rules"
            className="font-semibold text-brand hover:underline"
            target="_blank"
          >
            rules
          </Link>
          : no false information, abuse, spam or other people&apos;s personal information.
          CARCUX&apos;s analysts may use my opinions as evidence.
        </span>
      </label>
      <SubmitButton pending={pending} pendingText="Signing up…">
        Sign up
      </SubmitButton>
      <FormMessage state={state} />
    </form>
  );
}
