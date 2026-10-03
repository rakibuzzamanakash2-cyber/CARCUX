import Link from "next/link";

import type { Overview } from "@/lib/types";

function Counter({
  value,
  label,
  dot,
  href,
}: {
  value: number;
  label: string;
  dot: string;
  href: string;
}) {
  return (
    <Link
      href={href}
      className="flex shrink-0 flex-col justify-center rounded-md px-4 py-1 transition-colors hover:bg-white/5"
    >
      <span className="flex items-center gap-2">
        <span
          aria-hidden="true"
          className={`h-2.5 w-2.5 rounded-full ${value === 0 ? "bg-night-muted/40" : dot}`}
        />
        <span className="text-xl leading-none font-bold text-white">{value}</span>
      </span>
      <span className="mt-1 text-xs whitespace-nowrap text-night-muted">{label}</span>
    </Link>
  );
}

/** What needs attention now. Reviewers also see flags and the review backlog. */
export function StatusBar({ overview }: { overview: Overview | null }) {
  if (!overview) {
    return <p className="px-4 text-sm text-critical">Backend not reachable</p>;
  }
  const p = overview.open_by_priority;
  const items = [
    { value: p.critical, label: "Critical", dot: "bg-critical", href: "/events?priority=critical" },
    { value: p.high, label: "High", dot: "bg-alert-bright", href: "/events?priority=high" },
    { value: overview.open_events, label: "Open events", dot: "bg-medium", href: "/events" },
    {
      value: overview.reports_24h,
      label: "Reports (24h)",
      dot: "bg-[#2fbf68]",
      href: "/field-reports",
    },
    { value: overview.signals_24h, label: "Signals (24h)", dot: "bg-[#7cc7f2]", href: "/signals" },
    ...(overview.flagged_24h !== null
      ? [
          {
            value: overview.flagged_24h,
            label: "Flagged",
            dot: "bg-critical",
            href: "/field-reports?flagged=1",
          },
        ]
      : []),
    ...(overview.unreviewed_reports !== null
      ? [
          {
            value: overview.unreviewed_reports,
            label: "To review",
            dot: "bg-alert-bright",
            href: "/review",
          },
        ]
      : []),
  ];
  return (
    <div
      className="flex items-center divide-x divide-white/10 overflow-x-auto"
      aria-label="Current situation"
    >
      {items.map((i) => (
        <Counter key={i.label} {...i} />
      ))}
    </div>
  );
}
