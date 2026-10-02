"use client";

import { useState, useTransition } from "react";

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
          className="rounded-sm border border-line bg-panel-2 px-2 py-1 text-bone focus:border-steel focus:outline-none disabled:opacity-60"
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
              className="rounded-sm border border-line px-2.5 py-1 text-steel transition-colors hover:border-signal hover:text-bone disabled:opacity-60"
            >
              Deactivate
            </button>
          ) : (
            <button
              type="button"
              disabled={pending}
              onClick={() => save({ is_active: true })}
              className="rounded-sm border border-line px-2.5 py-1 text-steel transition-colors hover:border-ok hover:text-bone disabled:opacity-60"
            >
              Reactivate
            </button>
          )}
          {result && !result.ok && (
            <span role="alert" className="text-xs text-signal">
              {result.message}
            </span>
          )}
        </div>
      </td>
    </tr>
  );
}
