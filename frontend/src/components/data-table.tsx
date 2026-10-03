import { ChevronRight } from "lucide-react";
import Link from "next/link";

/** Table chrome shared by list pages. Columns are the page's own <th>/<td>. */
export function DataTable({
  head,
  children,
  empty,
}: {
  head: React.ReactNode;
  children: React.ReactNode;
  empty?: React.ReactNode;
}) {
  return (
    <div className="overflow-hidden rounded-xl border border-line bg-panel shadow-sm">
      {empty ?? (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-line bg-panel-2 text-[13px] font-semibold text-muted">
              {head}
            </thead>
            <tbody className="divide-y divide-line">{children}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export const th = "px-4 py-3 font-semibold";
export const td = "px-4 py-4 align-middle";
/** Columns that only fit from tablet width up. */
export const wide = "hidden md:table-cell";
export const rowCls = "transition-colors hover:bg-brand-soft/40";

export function EmptyState({ children }: { children: React.ReactNode }) {
  return <p className="px-5 py-12 text-center text-muted">{children}</p>;
}

/** The round "open" button at the end of a row. */
export function RowOpen({ href, label }: { href: string; label: string }) {
  return (
    <Link
      href={href}
      className="flex h-8 w-8 items-center justify-center rounded-full border border-line text-muted transition-colors hover:border-brand hover:text-brand"
    >
      <ChevronRight size={17} strokeWidth={2} aria-hidden="true" />
      <span className="sr-only">Open {label}</span>
    </Link>
  );
}

/** Initials in a circle, for people in tables. */
export function Initials({ name }: { name: string }) {
  const initials = name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join("");
  return (
    <span
      aria-hidden="true"
      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-soft text-xs font-bold text-brand"
    >
      {initials}
    </span>
  );
}

const PILL = {
  green: "bg-brand-soft text-brand",
  amber: "bg-alert-soft text-alert",
  red: "bg-critical-soft text-critical",
  grey: "bg-panel-2 text-muted",
  blue: "bg-medium-soft text-medium",
} as const;

export function Pill({ tone, children }: { tone: keyof typeof PILL; children: React.ReactNode }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[13px] font-semibold ${PILL[tone]}`}
    >
      {children}
    </span>
  );
}
