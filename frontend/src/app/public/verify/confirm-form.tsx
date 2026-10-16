"use client";

import { useActionState } from "react";

import { confirmEmail } from "@/app/actions/public";
import { FormMessage, SubmitButton } from "@/components/form";

export function ConfirmForm({ token }: { token: string }) {
  const [state, action, pending] = useActionState(confirmEmail, undefined);
  return (
    <form action={action} className="flex flex-col gap-3">
      <input type="hidden" name="token" value={token} />
      <SubmitButton pending={pending} pendingText="Confirming…">
        Confirm my account
      </SubmitButton>
      <FormMessage state={state} />
    </form>
  );
}
