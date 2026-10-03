import { ChevronDown, KeyRound, LogOut } from "lucide-react";
import Link from "next/link";

import { logout } from "@/app/actions/auth";

/** Avatar, name and role; opens to sign out. A <details> element: no script needed. */
export function UserMenu({ name, role }: { name: string; role: string }) {
  const initials = name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join("");
  return (
    <details className="group relative">
      <summary className="flex cursor-pointer list-none items-center gap-3 rounded-lg px-2 py-1.5 transition-colors hover:bg-white/5 [&::-webkit-details-marker]:hidden">
        <span
          aria-hidden="true"
          className="flex h-10 w-10 items-center justify-center rounded-full bg-forest-2 text-sm font-bold text-white ring-2 ring-white/15"
        >
          {initials}
        </span>
        <span className="hidden text-left leading-tight sm:block">
          <span className="block font-semibold text-white">{name}</span>
          <span className="block text-xs text-night-muted">{role}</span>
        </span>
        <ChevronDown
          size={16}
          aria-hidden="true"
          className="hidden text-night-muted transition-transform group-open:rotate-180 sm:block"
        />
        <span className="sr-only">Account menu</span>
      </summary>
      <div className="absolute right-0 z-[1100] mt-2 w-56 overflow-hidden rounded-lg border border-line bg-panel text-ink shadow-xl">
        <div className="border-b border-line px-4 py-3">
          <p className="font-semibold">{name}</p>
          <p className="text-sm text-muted">{role}</p>
        </div>
        <Link
          href="/account"
          className="flex items-center gap-2 px-4 py-3 text-sm font-semibold hover:bg-panel-2"
        >
          <KeyRound size={16} aria-hidden="true" />
          Account and password
        </Link>
        <form action={logout} className="border-t border-line">
          <button
            type="submit"
            className="flex w-full items-center gap-2 px-4 py-3 text-left text-sm font-semibold text-red hover:bg-red-soft"
          >
            <LogOut size={16} aria-hidden="true" />
            Sign out
          </button>
        </form>
      </div>
    </details>
  );
}
