import { LogOut } from "lucide-react";
import Image from "next/image";
import Link from "next/link";

import { logout } from "@/app/actions/auth";
import { DhakaClock } from "@/components/dhaka-clock";
import { Sidebar } from "@/components/sidebar";
import { StatusBar } from "@/components/status-bar";
import { api } from "@/lib/api";
import { verifySession } from "@/lib/dal";
import { roleLabel, type Overview } from "@/lib/types";

async function loadOverview(): Promise<Overview | null> {
  try {
    return await api<Overview>("/overview");
  } catch {
    return null;
  }
}

export default async function ConsoleLayout({ children }: { children: React.ReactNode }) {
  const [user, overview] = await Promise.all([verifySession(), loadOverview()]);
  const initials = user.full_name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join("");

  return (
    <div className="grid min-h-dvh grid-rows-[auto_1fr] md:h-dvh md:overflow-hidden">
      <header className="sticky top-0 z-[1001] flex items-center gap-4 border-b border-line bg-panel px-3 py-2 md:static md:px-0 md:py-0">
        <Link
          href="/"
          className="flex shrink-0 items-center md:h-16 md:w-60 md:justify-center md:border-r md:border-line"
          aria-label="CARCUX situation map"
        >
          <Image
            src="/carcux-logo.png"
            alt="CARCUX"
            width={900}
            height={211}
            priority
            className="h-8 w-auto md:h-9"
          />
        </Link>
        <div className="hidden min-w-0 flex-1 lg:block">
          <StatusBar overview={overview} />
        </div>
        <div className="ml-auto flex items-center gap-4 md:pr-4">
          <span className="hidden xl:block">
            <DhakaClock />
          </span>
          <div className="flex items-center gap-2.5">
            <span
              aria-hidden="true"
              className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-soft text-sm font-semibold text-brand"
            >
              {initials}
            </span>
            <p className="hidden text-sm leading-tight sm:block">
              <span className="block font-semibold text-ink">{user.full_name}</span>
              <span className="block text-xs text-muted">{roleLabel(user.role)}</span>
            </p>
          </div>
          <form action={logout}>
            <button
              type="submit"
              title="Sign out"
              className="flex h-9 w-9 items-center justify-center rounded-md border border-line text-muted transition-colors hover:border-critical/50 hover:text-critical"
            >
              <LogOut size={17} strokeWidth={1.75} aria-hidden="true" />
              <span className="sr-only">Sign out</span>
            </button>
          </form>
        </div>
      </header>

      <div className="grid min-h-0 md:grid-cols-[15rem_1fr]">
        <Sidebar role={user.role} />
        <div className="min-h-0 min-w-0 pb-20 md:overflow-y-auto md:pb-0">
          <div className="overflow-x-auto border-b border-line bg-panel px-2 py-1.5 lg:hidden">
            <StatusBar overview={overview} />
          </div>
          {children}
        </div>
      </div>
    </div>
  );
}
