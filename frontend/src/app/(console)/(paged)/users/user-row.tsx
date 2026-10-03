"use client";

import { useState, useTransition } from "react";

import { resetPassword } from "@/app/actions/review";
import { updateUser } from "@/app/actions/users";
import { ROLES, type ActionState, type Role, type User } from "@/lib/types";

const dateFmt = new Intl.DateTimeFormat("en-GB", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Asia/Dhaka",
});

export function UserRow({ user, isSelf }: { user: User; isSelf: boolean }) {
  const [pending, startTransition] = useTransition();
  const [result, setResult] = useState<ActionState>();
  const [resetting, setResetting] = useState(false);
  const [temp, setTemp] = useState("");

  function save(changes: { role?: Role; is_active?: boolean }, confirmText?: string) {
    if (confirmText && !window.confirm(confirmText)) return;
    startTransition(async () => setResult(await updateUser(user.id, changes)));
  }

  return (
    <tr className={user.is_active ? "" : "text-steel"} aria-busy={pending}>
      <td className="py-3 pr-4">
        {user.full_name}
        {isSelf && <span className="ml-2 text-xs text-steel">(you)</span>}
      </td>
      <td className="py-3 pr-4 text-steel">{user.email}</td>
      <td className="py-3 pr-4">
        <label className="sr-only" htmlFor={`role-${user.id}`}>
          Role for {user.full_name}
        </label>
        <select
          id={`role-${user.id}`}
          value={user.role}
          disabled={pending}
          onChange={(e) =>
            save(
              { role: e.target.value as Role },
              `Change ${user.full_name}'s role? They will be signed out.`,
            )
          }
          className="rounded-md border border-line bg-panel px-2 py-1 text-ink shadow-sm focus:border-brand focus:outline-none disabled:opacity-60"
        >
          {ROLES.map((r) => (
            <option key={r.value} value={r.value}>
              {r.label}
            </option>
          ))}
        </select>
      </td>
      <td className="py-3 pr-4 text-steel">
        {user.last_login_at ? dateFmt.format(new Date(user.last_login_at)) : "Never"}
      </td>
      <td className="py-3">
        <div className="flex flex-wrap items-center gap-3">
          {user.is_active ? (
            <button
              type="button"
              disabled={pending}
              onClick={() =>
                save(
                  { is_active: false },
                  `Deactivate ${user.full_name}? They will be signed out and cannot sign in again until reactivated.`,
                )
              }
              className="rounded-md border border-line px-2.5 py-1 text-steel transition-colors hover:border-signal hover:text-bone disabled:opacity-60"
            >
              Deactivate
            </button>
          ) : (
            <button
              type="button"
              disabled={pending}
              onClick={() => save({ is_active: true })}
              className="rounded-md border border-line px-2.5 py-1 text-steel transition-colors hover:border-ok hover:text-bone disabled:opacity-60"
            >
              Reactivate
            </button>
          )}
          <button
            type="button"
            disabled={pending}
            onClick={() => setResetting((v) => !v)}
            aria-expanded={resetting}
            className="rounded-md border border-line px-2.5 py-1 text-steel transition-colors hover:border-alert hover:text-bone disabled:opacity-60"
          >
            Reset password
          </button>
          {resetting && (
            <form
              className="flex w-full flex-wrap items-center gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                startTransition(async () => {
                  const r = await resetPassword(user.id, temp);
                  setResult(r);
                  if (r?.ok) {
                    setResetting(false);
                    setTemp("");
                  }
                });
              }}
            >
              <label className="sr-only" htmlFor={`temp-${user.id}`}>
                Temporary password for {user.full_name}
              </label>
              <input
                id={`temp-${user.id}`}
                type="text"
                autoComplete="off"
                minLength={12}
                required
                value={temp}
                onChange={(e) => setTemp(e.target.value)}
                placeholder="Temporary password, 12+ characters"
                className="h-8 min-w-56 flex-1 rounded-md border border-line bg-panel px-2 text-sm focus:border-brand focus:outline-none"
              />
              <button
                type="submit"
                disabled={pending || temp.length < 12}
                className="h-8 rounded-md bg-brand px-3 text-sm font-semibold text-white disabled:opacity-50"
              >
                Set
              </button>
            </form>
          )}
          {result && (
            <span
              role={result.ok ? "status" : "alert"}
              className={`text-xs ${result.ok ? "text-brand" : "text-signal"}`}
            >
              {result.message}
            </span>
          )}
        </div>
      </td>
    </tr>
  );
}
