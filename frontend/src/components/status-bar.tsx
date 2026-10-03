import Link from "next/link";

import type { Overview } from "@/lib/types";

function Counter({
  value,
  label,
  tone,
  href,
}: {
  value: number;
  label: string;
  tone: "critical" | "alert" | "water" | "plain";
  href: string;
}) {
  const dot = {
    critical: "bg-critical",
    alert: "bg-alert",
    water: "bg-brand",
    plain: "bg-muted",
  }[tone];
  const quiet = value === 0;
  return (
    <Link
      href={href}
      className={`flex items-baseline gap-1.5 rounded-md px-2 py-1 transition-colors hover:bg-panel-2 ${
        quiet ? "text-muted" : "text-ink"
      }`}
    >
      <span
        aria-hidden="true"
        className={`relative top-[-1px] inline-block h-2 w-2 rounded-full ${quiet ? "bg-line" : dot}`}
      />
      <span className="text-xl font-bold">{value}</span>
      <span className="text-[13px] text-muted">{label}</span>
    </Link>
  );
}

/** What needs attention now, in one line. Hidden counters stay out rather than showing "–". */
export function StatusBar({ overview }: { overview: Overview | null }) {
  if (!overview) {
    return <p className="text-sm text-critical">Backend not reachable</p>;
  }
  const p = overview.open_by_priority;
  return (
    <div
      className="flex items-center gap-x-1 whitespace-nowrap lg:flex-wrap"
      aria-label="Current situation"
    >
      <Counter value={p.critical} label="critical" tone="critical" href="/events" />
      <Counter value={p.high} label="high" tone="alert" href="/events" />
      <Counter value={overview.open_events} label="open events" tone="plain" href="/events" />
      <span aria-hidden="true" className="mx-1 hidden h-5 w-px bg-line sm:block" />
      <Counter
        value={overview.reports_24h}
        label="reports, 24 h"
        tone="water"
        href="/field-reports"
      />
      {overview.flagged_24h !== null && (
        <Counter
          value={overview.flagged_24h}
          label="flagged"
          tone="critical"
          href="/field-reports?flagged=1"
        />
      )}
      {overview.unreviewed_reports !== null && (
        <Counter
          value={overview.unreviewed_reports}
          label="to review"
          tone="alert"
          href="/review"
        />
      )}
    </div>
  );
}
