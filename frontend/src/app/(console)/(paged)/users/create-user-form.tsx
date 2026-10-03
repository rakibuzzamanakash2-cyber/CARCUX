"use client";

import { useActionState, useState } from "react";

import { createUser } from "@/app/actions/users";
import { Field, FormMessage, SelectField, SubmitButton } from "@/components/form";
import { ROLES, type ActionState } from "@/lib/types";

export function CreateUserForm() {
  // Controlled fields survive React's automatic reset when the server rejects the
  // form (e.g. duplicate email); they are cleared only after a successful create.
  // The password stays uncontrolled, so it is always cleared.
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("");

  const [state, action, pending] = useActionState(async (prev: ActionState, formData: FormData) => {
    const result = await createUser(prev, formData);
    if (result?.ok) {
      setFullName("");
      setEmail("");
      setRole("");
    }
    return result;
  }, undefined);

  return (
    <form action={action} className="grid max-w-3xl gap-5 sm:grid-cols-2">
      <Field
        label="Full name"
        name="full_name"
        required
        maxLength={200}
        value={fullName}
        onChange={(e) => setFullName(e.target.value)}
      />
      <Field
        label="Email"
        name="email"
        type="text"
        required
        placeholder="name@office.local"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
      />
      <Field
        label="Temporary password"
        name="password"
        type="password"
        required
        minLength={12}
        autoComplete="new-password"
        hint="At least 12 characters. Share it with the person privately."
      />
      <SelectField
        label="Role"
        name="role"
        required
        value={role}
        onChange={(e) => setRole(e.target.value)}
      >
        {/* Not disabled: a disabled placeholder makes browsers silently show the
            first real role (Admin) after a reset. `required` still blocks "". */}
        <option value="">Choose a role</option>
        {ROLES.map((r) => (
          <option key={r.value} value={r.value}>
            {r.label}: {r.description}
          </option>
        ))}
      </SelectField>
      <div className="flex flex-col gap-4 sm:col-span-2 sm:flex-row sm:items-center">
        <SubmitButton pending={pending} pendingText="Creating…">
          Create account
        </SubmitButton>
        <FormMessage state={state} />
      </div>
    </form>
  );
}
