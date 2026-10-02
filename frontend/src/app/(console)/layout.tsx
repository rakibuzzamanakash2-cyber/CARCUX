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

  return (
    <div className="grid min-h-dvh grid-rows-[auto_1fr] md:h-dvh md:overflow-hidden">
      <header className="sticky top-0 z-[1001] flex items-center gap-4 border-b border-line bg-panel px-3 py-2 md:static md:px-4">
        <Link href="/" className="flex shrink-0 items-center" aria-label="CARCUX map">
          <Image
            src="/carcux-logo-light.png"
            alt="CARCUX"
            width={900}
            height={474}
            priority
            className="h-8 w-auto"
          />
        </Link>
        <div className="hidden min-w-0 flex-1 lg:block">
          <StatusBar overview={overview} />
        </div>
        <div className="ml-auto flex items-center gap-4">
          <span className="hidden xl:block">
            <DhakaClock />
          </span>
          <p className="text-right text-sm leading-tight">
            <span className="block text-ink">{user.full_name}</span>
            <span className="block text-xs text-muted">{roleLabel(user.role)}</span>
          </p>
          <form action={logout}>
            <button
              type="submit"
              title="Sign out"
              className="flex h-9 w-9 items-center justify-center rounded-md border border-line text-muted transition-colors hover:border-muted hover:text-ink"
            >
              <LogOut size={17} strokeWidth={1.75} aria-hidden="true" />
              <span className="sr-only">Sign out</span>
            </button>
          </form>
        </div>
      </header>

      <div className="grid min-h-0 md:grid-cols-[5.5rem_1fr]">
        <Sidebar role={user.role} />
        <div className="min-h-0 min-w-0 pb-20 md:overflow-y-auto md:pb-0">
          <div className="overflow-x-auto border-b border-line px-2 py-1.5 lg:hidden">
            <StatusBar overview={overview} />
          </div>
          {children}
        </div>
      </div>
    </div>
  );
}
