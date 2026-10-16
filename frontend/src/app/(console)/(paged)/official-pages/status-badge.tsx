import { BadgeCheck, CircleDashed, Ban } from "lucide-react";

import type { PageStatus } from "@/lib/types";

const STYLE: Record<PageStatus, { label: string; cls: string; Icon: typeof BadgeCheck }> = {
  verified: { label: "Verified", cls: "bg-ok/15 text-ok ring-ok/40", Icon: BadgeCheck },
  pending: {
    label: "Not verified yet",
    cls: "bg-panel-2 text-muted ring-line",
    Icon: CircleDashed,
  },
  suspended: {
    label: "Suspended",
    cls: "bg-critical-soft text-critical ring-critical/40",
    Icon: Ban,
  },
};

export function PageStatusBadge({ status, onBand }: { status: PageStatus; onBand?: boolean }) {
  const { label, cls: base, Icon } = STYLE[status];
  // On the dark page banner the badge sits on white so it stays readable.
  const cls = onBand
    ? `bg-white ${base
        .split(" ")
        .filter((c) => c.startsWith("text-") || c.startsWith("ring-"))
        .join(" ")}`
    : base;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ${cls}`}
    >
      <Icon size={13} aria-hidden="true" />
      {label}
    </span>
  );
}
