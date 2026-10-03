import { Bell } from "lucide-react";
import Image from "next/image";
import Link from "next/link";

import { DhakaClock } from "@/components/dhaka-clock";
import { Sidebar } from "@/components/sidebar";
import { StatusBar } from "@/components/status-bar";
import { UserMenu } from "@/components/user-menu";
import { api } from "@/lib/api";
import { verifySession } from "@/lib/dal";
import { REPORT_REVIEWERS, roleLabel, type Overview } from "@/lib/types";

async function loadOverview(): Promise<Overview | null> {
  try {
    return await api<Overview>("/overview");
  } catch {
    return null;
  }
}

export default async function ConsoleLayout({ children }: { children: React.ReactNode }) {
  const [user, overview] = await Promise.all([verifySession(), loadOverview()]);
  const reviewer = REPORT_REVIEWERS.includes(user.role);
  const urgent = overview ? overview.open_by_priority.critical + overview.open_by_priority.high : 0;
  const toReview = overview?.unreviewed_reports ?? 0;

  return (
    <div className="grid min-h-dvh grid-rows-[auto_1fr] md:h-dvh md:overflow-hidden">
      <header className="sticky top-0 z-[1001] flex items-center gap-2 border-b border-[#1f7a46]/60 bg-gradient-to-r from-night via-[#0d2a1d] to-night text-white md:static">
        <Link
          href="/"
          className="flex shrink-0 flex-col justify-center px-3 py-2 md:w-60 md:px-5"
          aria-label="CARCUX situation map"
        >
          <Image
            src="/carcux-logo-on-dark.png"
            alt="CARCUX"
            width={900}
            height={211}
            priority
            className="h-8 w-auto md:h-10"
          />
          <span className="mt-1 hidden text-[8.5px] font-semibold tracking-[0.12em] whitespace-nowrap text-night-muted md:block">
            SAFER COMMUNITIES · SMARTER RESPONSE
          </span>
        </Link>
        <div className="hidden min-w-0 flex-1 border-l border-white/10 lg:block">
          <StatusBar overview={overview} />
        </div>
        <div className="ml-auto flex items-center gap-2 pr-2 md:gap-4 md:pr-4">
          <div className="hidden border-r border-white/10 pr-4 xl:block">
            <DhakaClock />
          </div>
          <UserMenu name={user.full_name} role={roleLabel(user.role)} />
          {reviewer && (
            <Link
              href="/review"
              className="relative flex h-10 w-10 items-center justify-center rounded-lg text-night-ink transition-colors hover:bg-white/5"
              title={toReview ? `${toReview} reports waiting for review` : "Review queue"}
            >
              <Bell size={21} strokeWidth={1.8} aria-hidden="true" />
              {toReview > 0 && (
                <span
                  aria-hidden="true"
                  className="absolute top-2 right-2 h-2.5 w-2.5 rounded-full bg-critical ring-2 ring-night"
                />
              )}
              <span className="sr-only">
                {toReview ? `${toReview} reports waiting for review` : "Review queue"}
              </span>
            </Link>
          )}
        </div>
      </header>

      <div className="grid min-h-0 md:grid-cols-[15rem_1fr]">
        <Sidebar role={user.role} badges={{ "/events": urgent, "/review": toReview }} />
        <div className="min-h-0 min-w-0 pb-20 md:overflow-y-auto md:pb-0">
          <div className="overflow-x-auto border-b border-white/10 bg-night px-1 py-1 lg:hidden">
            <StatusBar overview={overview} />
          </div>
          {children}
        </div>
      </div>
    </div>
  );
}
