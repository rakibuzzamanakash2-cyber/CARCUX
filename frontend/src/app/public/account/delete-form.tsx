"use client";

import { useActionState } from "react";

import { deleteAccount } from "@/app/actions/public";
import { Field, FormMessage } from "@/components/form";

export function DeleteAccountForm() {
  const [state, action, pending] = useActionState(deleteAccount, undefined);
  return (
    <form action={action} className="flex flex-col gap-3">
      <Field
        label="Your password"
        name="password"
        type="password"
        required
        autoComplete="current-password"
      />
      <button
        type="submit"
        disabled={pending}
        className="h-11 rounded-md border border-critical px-5 font-semibold text-critical hover:bg-critical-soft disabled:opacity-60"
      >
        {pending ? "Deleting…" : "Delete my account"}
      </button>
      <FormMessage state={state} />
    </form>
  );
}
