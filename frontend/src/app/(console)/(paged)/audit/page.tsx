import {
  ClipboardList,
  KeyRound,
  LogIn,
  Radar,
  RadioTower,
  Rss,
  ScrollText,
  ShieldAlert,
  UserCog,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";

import { DataTable, EmptyState, Initials, rowCls, td, th, wide } from "@/components/data-table";
import { FilterBar } from "@/components/filter-bar";
import { PageBand, PageBody, StatTile, StatTiles } from "@/components/page-header";
import { Pager } from "@/components/pager";
import { api } from "@/lib/api";
import { requireRole } from "@/lib/dal";
import { formatDhaka } from "@/lib/format";
import type { AuditEntry, AuditPage } from "@/lib/types";

export const metadata = { title: "Audit log" };

const PAGE_SIZE = 50;

/** Plain words and an icon for every action the backend records. */
const ACTIONS: Record<string, { label: string; icon: LucideIcon; tone: string }> = {
  "auth.login_succeeded": { label: "Signed in", icon: LogIn, tone: "text-brand" },
  "auth.login_failed": { label: "Failed sign-in", icon: ShieldAlert, tone: "text-critical" },
  "auth.password_changed": { label: "Changed their password", icon: KeyRound, tone: "text-brand" },
  "auth.password_change_failed": {
    label: "Failed password change",
    icon: ShieldAlert,
    tone: "text-critical",
  },
  "user.created": { label: "Created an account", icon: UserCog, tone: "text-medium" },
  "user.updated": { label: "Changed an account", icon: UserCog, tone: "text-medium" },
  "user.bootstrapped": { label: "First admin created", icon: UserCog, tone: "text-medium" },
  "user.password_reset": { label: "Reset a password", icon: KeyRound, tone: "text-alert" },
  "field_report.submitted": {
    label: "Sent a field report",
    icon: ClipboardList,
    tone: "text-brand",
  },
  "field_report.verified": {
    label: "Checked a report's fingerprint",
    icon: ClipboardList,
    tone: "text-medium",
  },
  "field_report.reviewed": {
    label: "Triaged a field report",
    icon: ClipboardList,
    tone: "text-alert",
  },
  "event.created": { label: "Created an event", icon: Radar, tone: "text-brand" },
  "event.updated": { label: "Changed an event", icon: Radar, tone: "text-medium" },
  "event.evidence_linked": {
    label: "Linked evidence to an event",
    icon: Radar,
    tone: "text-brand",
  },
  "event.evidence_updated": {
    label: "Changed how evidence bears on an event",
    icon: Radar,
    tone: "text-medium",
  },
  "event.evidence_unlinked": {
    label: "Unlinked evidence from an event",
    icon: Radar,
    tone: "text-alert",
  },
  "signal.entered": { label: "Entered a bulletin", icon: RadioTower, tone: "text-brand" },
  "signal.reviewed": { label: "Triaged a signal", icon: RadioTower, tone: "text-alert" },
  "source.created": { label: "Added a news feed", icon: Rss, tone: "text-brand" },
  "source.updated": { label: "Changed a source", icon: Rss, tone: "text-medium" },
  "source.fetched": { label: "Read a source now", icon: Rss, tone: "text-medium" },
  "signal.imported": {
    label: "Imported a list of news items",
    icon: RadioTower,
    tone: "text-brand",
  },
  "source.backfilled": { label: "Filled in a past period", icon: Rss, tone: "text-medium" },
  "dataset.exported": { label: "Exported the dataset", icon: ScrollText, tone: "text-brand" },
};

const GROUPS = [
  { value: "", label: "Every action" },
  { value: "auth.", label: "Sign-ins and passwords" },
  { value: "user.", label: "Accounts" },
  { value: "field_report.", label: "Field reports" },
  { value: "event.", label: "Events and evidence" },
  { value: "signal.", label: "Public signals" },
  { value: "source.", label: "Sources" },
];

const PERIODS = [
  { value: "", label: "Any time", hours: 0 },
  { value: "24h", label: "Last 24 hours", hours: 24 },
  { value: "7d", label: "Last 7 days", hours: 24 * 7 },
  { value: "30d", label: "Last 30 days", hours: 24 * 30 },
];

type Params = { action?: string; period?: string; target?: string; page?: string };

function href(p: Params): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(p)) if (v) q.set(k, v);
  const s = q.toString();
  return s ? `/audit?${s}` : "/audit";
}

function sinceFor(period: string): string | null {
  const hours = PERIODS.find((p) => p.value === period)?.hours ?? 0;
  return hours ? new Date(Date.now() - hours * 3_600_000).toISOString() : null;
}

const TARGETS: Record<string, { label: string; href?: (id: string) => string }> = {
  event: { label: "Event", href: (id) => `/events/${id}` },
  field_report: { label: "Field report", href: (id) => `/field-reports/${id}` },
  signal: { label: "Signal", href: (id) => `/signals/${id}` },
  source: { label: "Source", href: () => "/sources" },
  user: { label: "Account" },
};

/** Where the entry points: a link to the event, report, signal or account it concerns. */
function Target({ entry }: { entry: AuditEntry }) {
  const id = entry.target_id;
  if (!entry.target_type || !id) return <span className="text-muted">None</span>;
  const short = id.slice(0, 8);
  const target = TARGETS[entry.target_type];
  const label = target?.label ?? entry.target_type;
  const to = target?.href?.(id);
  return to ? (
    <Link href={to} className="font-semibold text-brand hover:underline">
      {label} {short}
    </Link>
  ) : (
    <span>
      {label} <span className="text-muted">{short}</span>
    </span>
  );
}

/** The useful part of the details, in a line, with the raw record one click away. */
function Details({ entry }: { entry: AuditEntry }) {
  const d = entry.details as Record<string, unknown>;
  let summary = "";
  if (entry.action === "auth.login_failed")
    summary = `Reason: ${String(d.reason ?? "unknown").replace(/_/g, " ")}`;
  else if (entry.action === "field_report.reviewed" || entry.action === "signal.reviewed")
    summary = `${String(d.from)} → ${String(d.to)}${d.note ? `: ${String(d.note)}` : ""}`;
  else if (entry.action === "event.created" || entry.action === "signal.entered")
    summary = String(d.title ?? "");
  else if (entry.action === "source.created") summary = String(d.url ?? "");
  else if (entry.action === "event.evidence_linked")
    summary = `As ${String(d.relation ?? "").replace(/_/g, " ")}`;
  else if (d.changes && typeof d.changes === "object")
    summary = `Changed ${Object.keys(d.changes as object)
      .join(", ")
      .replace(/_/g, " ")}`;
  else if (entry.action === "field_report.verified")
    summary = d.intact ? "Unchanged" : "Changed after submission";
  else if (entry.action === "user.created") summary = `Role: ${String(d.role ?? "")}`;
  const raw = Object.keys(d).length > 0;
  return (
    <div className="max-w-xs">
      {summary && <p className="line-clamp-2">{summary}</p>}
      {raw && (
        <details className="mt-1">
          <summary className="cursor-pointer text-xs text-muted hover:text-ink">
            Full record
          </summary>
          <pre className="mt-1 max-h-48 overflow-auto rounded-md bg-panel-2 p-2 text-xs whitespace-pre-wrap">
            {JSON.stringify(d, null, 2)}
          </pre>
        </details>
      )}
      {!summary && !raw && <span className="text-muted">None</span>}
    </div>
  );
}

export default async function AuditPageView({ searchParams }: { searchParams: Promise<Params> }) {
  await requireRole("admin");
  const params = await searchParams;
  const page = Math.max(1, Number.parseInt(params.page ?? "1", 10) || 1);
  const period = PERIODS.some((p) => p.value === params.period) ? params.period! : "";
  const action = params.action ?? "";
  const target = (params.target ?? "").trim();

  const query = new URLSearchParams({
    limit: String(PAGE_SIZE),
    offset: String((page - 1) * PAGE_SIZE),
  });
  if (action) query.set("action", action);
  if (target) query.set("target_id", target);
  const since = sinceFor(period);
  if (since) query.set("since", since);
  const day = sinceFor("24h")!;

  const [data, logins, failed] = await Promise.all([
    api<AuditPage>(`/audit?${query}`),
    api<AuditPage>(`/audit?action=auth.login_succeeded&limit=1&since=${encodeURIComponent(day)}`),
    api<AuditPage>(`/audit?action=auth.login_failed&limit=1&since=${encodeURIComponent(day)}`),
  ]);
  const lastPage = Math.max(1, Math.ceil(data.total / PAGE_SIZE));
  const current: Params = { action, period, target };
  const actionOptions = [
    ...GROUPS,
    ...data.actions.map((a) => ({ value: a, label: ACTIONS[a]?.label ?? a })),
  ];

  return (
    <>
      <PageBand
        scene="hills"
        icon={ScrollText}
        title="Audit log"
        description="Everything people did in CARCUX, newest first. Entries can never be changed or deleted."
      />
      <PageBody>
        <StatTiles>
          <StatTile
            icon={ScrollText}
            value={data.total}
            label="Entries"
            note="Matching the filters"
            tone="green"
          />
          <StatTile
            icon={LogIn}
            value={logins.total}
            label="Sign-ins"
            note="In the last 24 hours"
            tone="blue"
          />
          <StatTile
            icon={ShieldAlert}
            value={failed.total}
            label="Failed sign-ins"
            note="In the last 24 hours"
            tone="red"
            href={href({ action: "auth.login_failed", period: "24h" })}
          />
          <StatTile
            icon={KeyRound}
            value={data.actions.length}
            label="Kinds of action"
            note="Recorded so far"
            tone="amber"
          />
        </StatTiles>

        <FilterBar
          action="/audit"
          search={{ name: "target", value: target, placeholder: "Event, report or account id" }}
          selects={[
            { name: "action", label: "What", value: action, options: actionOptions },
            {
              name: "period",
              label: "When",
              value: period,
              options: PERIODS.map(({ value, label }) => ({ value, label })),
            },
          ]}
        />

        <DataTable
          head={
            <tr>
              <th scope="col" className={th}>
                When
              </th>
              <th scope="col" className={th}>
                Who
              </th>
              <th scope="col" className={th}>
                What
              </th>
              <th scope="col" className={th}>
                Concerning
              </th>
              <th scope="col" className={`${th} ${wide}`}>
                Details
              </th>
              <th scope="col" className={`${th} ${wide}`}>
                From
              </th>
            </tr>
          }
          empty={data.items.length === 0 ? <EmptyState>No entries match.</EmptyState> : undefined}
        >
          {data.items.map((e) => {
            const a = ACTIONS[e.action] ?? {
              label: e.action,
              icon: ScrollText,
              tone: "text-muted",
            };
            const Icon = a.icon;
            return (
              <tr key={e.id} className={rowCls}>
                <td className={`${td} whitespace-nowrap text-muted`}>
                  {formatDhaka(e.occurred_at)}
                </td>
                <td className={td}>
                  {e.actor ? (
                    <span className="flex items-center gap-2">
                      <Initials name={e.actor.full_name} />
                      {e.actor.full_name}
                    </span>
                  ) : (
                    <span className="text-muted">Unknown</span>
                  )}
                </td>
                <td className={td}>
                  <span className="inline-flex items-center gap-2 font-semibold">
                    <Icon size={16} aria-hidden="true" className={a.tone} />
                    {a.label}
                  </span>
                </td>
                <td className={td}>
                  <Target entry={e} />
                </td>
                <td className={`${td} ${wide} text-sm`}>
                  <Details entry={e} />
                </td>
                <td className={`${td} ${wide} text-muted`}>{e.ip_address ?? "Unknown"}</td>
              </tr>
            );
          })}
        </DataTable>

        {data.total > PAGE_SIZE && (
          <Pager
            page={page}
            lastPage={lastPage}
            total={data.total}
            noun="entries"
            newer={page > 1 ? href({ ...current, page: String(page - 1) }) : null}
            older={page < lastPage ? href({ ...current, page: String(page + 1) }) : null}
          />
        )}
      </PageBody>
    </>
  );
}
