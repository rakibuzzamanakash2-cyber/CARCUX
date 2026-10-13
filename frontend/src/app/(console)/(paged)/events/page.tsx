import {
  CalendarDays,
  Clock,
  MapPin,
  Paperclip,
  Plus,
  Radar,
  ShieldCheck,
  Siren,
  RadioTower,
  UserRound,
} from "lucide-react";
import Link from "next/link";

import { DataTable, EmptyState, RowOpen, rowCls, td, th, wide } from "@/components/data-table";
import { AssessmentText, PriorityBadge, StatusText } from "@/components/event-badges";
import { FilterBar } from "@/components/filter-bar";
import { buttonOnBand, PageBand, PageBody, StatTile, StatTiles } from "@/components/page-header";
import { Pager } from "@/components/pager";
import { api } from "@/lib/api";
import { verifySession } from "@/lib/dal";
import { eventTypeIcon } from "@/lib/event-icons";
import { eventTypeLabel } from "@/lib/event-types";
import { FAMILIES, PRIORITIES } from "@/lib/events";
import { formatDhaka } from "@/lib/format";
import { REPORT_REVIEWERS, type EventPage, type EventStatus } from "@/lib/types";

export const metadata = { title: "Events" };

const PAGE_SIZE = 25;

const VIEWS: { key: string; label: string; statuses: EventStatus[] }[] = [
  { key: "open", label: "Open", statuses: ["active", "monitoring"] },
  { key: "resolved", label: "Resolved", statuses: ["resolved"] },
  { key: "dismissed", label: "Dismissed", statuses: ["dismissed"] },
  { key: "all", label: "All statuses", statuses: [] },
];

type Params = {
  view?: string;
  family?: string;
  priority?: string;
  q?: string;
  page?: string;
};

function href(p: Params): string {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(p))
    if (v && !(k === "view" && v === "open")) params.set(k, v);
  const query = params.toString();
  return query ? `/events?${query}` : "/events";
}

/** Figures for the tiles: open events only, so they describe the situation now. */
function summarise(open: EventPage) {
  const dayAgo = Date.now() - 24 * 3600 * 1000;
  return {
    open: open.total,
    urgent: open.items.filter((e) => e.priority === "critical" || e.priority === "high").length,
    critical: open.items.filter((e) => e.priority === "critical").length,
    verified: open.items.filter(
      (e) => e.assessment === "verified" || e.assessment === "partially_verified",
    ).length,
    fresh: open.items.filter((e) => new Date(e.created_at).getTime() > dayAgo).length,
  };
}

export default async function EventsPage({ searchParams }: { searchParams: Promise<Params> }) {
  const user = await verifySession();
  const params = await searchParams;
  const view = VIEWS.find((v) => v.key === params.view) ?? VIEWS[0];
  const family = FAMILIES.some((f) => f.value === params.family) ? params.family! : "";
  const priority = PRIORITIES.some((p) => p.value === params.priority) ? params.priority! : "";
  const q = (params.q ?? "").trim().slice(0, 100);
  const page = Math.max(1, Number.parseInt(params.page ?? "1", 10) || 1);

  const query = new URLSearchParams({
    limit: String(PAGE_SIZE),
    offset: String((page - 1) * PAGE_SIZE),
  });
  for (const s of view.statuses) query.append("status", s);
  if (family) query.set("family", family);
  if (priority) query.set("priority", priority);
  if (q) query.set("q", q);

  const [data, open] = await Promise.all([
    api<EventPage>(`/events?${query}`),
    api<EventPage>("/events?status=active&status=monitoring&limit=200"),
  ]);
  const stats = summarise(open);
  const reviewer = REPORT_REVIEWERS.includes(user.role);
  const lastPage = Math.max(1, Math.ceil(data.total / PAGE_SIZE));
  const current: Params = { view: view.key, family, priority, q };
  const filtered = Boolean(family || priority || q);

  return (
    <>
      <PageBand
        scene="sundarbans"
        icon={Radar}
        title="Events"
        description="Every situation being tracked, with the analysts' assessment and the evidence behind it."
        actions={
          reviewer && (
            <Link href="/events/new" className={buttonOnBand}>
              <Plus size={17} strokeWidth={2.25} aria-hidden="true" />
              New event
            </Link>
          )
        }
      />
      <PageBody>
        <StatTiles>
          <StatTile
            icon={Radar}
            value={stats.open}
            label="Open events"
            note="Active or monitoring"
            tone="green"
            href="/events"
          />
          <StatTile
            icon={Siren}
            value={stats.urgent}
            label="Critical or high"
            note={`${stats.critical} critical`}
            tone="red"
            href={href({ priority: "critical" })}
          />
          <StatTile
            icon={ShieldCheck}
            value={stats.verified}
            label="Verified"
            note="Fully or partly, of the open ones"
            tone="green"
          />
          <StatTile
            icon={Clock}
            value={stats.fresh}
            label="New today"
            note="Opened in the last 24 hours"
            tone="amber"
          />
        </StatTiles>

        <FilterBar
          action="/events"
          search={{
            name: "q",
            value: q,
            placeholder: "Search title, place or summary",
          }}
          selects={[
            {
              name: "view",
              label: "Status",
              value: view.key === "open" ? "" : view.key,
              options: VIEWS.map((v) => ({
                value: v.key === "open" ? "" : v.key,
                label: v.label,
              })),
            },
            {
              name: "family",
              label: "Kind",
              value: family,
              options: [{ value: "", label: "Every kind" }, ...FAMILIES],
            },
            {
              name: "priority",
              label: "Priority",
              value: priority,
              options: [{ value: "", label: "Any priority" }, ...PRIORITIES],
            },
          ]}
        />

        <DataTable
          head={
            <tr>
              <th scope="col" className={th}>
                Priority
              </th>
              <th scope="col" className={th}>
                Event
              </th>
              <th scope="col" className={th}>
                Assessment
              </th>
              <th scope="col" className={`${th} ${wide}`}>
                Evidence
              </th>
              <th scope="col" className={`${th} ${wide}`}>
                Status
              </th>
              <th scope="col" className={`${th} ${wide}`}>
                Started
              </th>
              <th scope="col" className={th}>
                <span className="sr-only">Open</span>
              </th>
            </tr>
          }
          empty={
            data.items.length === 0 ? (
              <EmptyState>
                {filtered
                  ? "No events match. Clear the filters to see more."
                  : view.key === "open"
                    ? reviewer
                      ? "No open events. Create one from a field report, or with New event."
                      : "No open events."
                    : "No events here."}
              </EmptyState>
            ) : undefined
          }
        >
          {data.items.map((e) => {
            const TypeIcon = eventTypeIcon(e.event_type);
            const ev = e.evidence_counts;
            const supporting = ev.supports + ev.partially_supports;
            return (
              <tr key={e.id} className={rowCls}>
                <td className={td}>
                  <PriorityBadge priority={e.priority} />
                </td>
                <td className={td}>
                  <Link
                    href={`/events/${e.id}`}
                    className="text-[15px] font-semibold text-ink hover:text-brand hover:underline"
                  >
                    {e.title}
                  </Link>
                  <span className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-muted">
                    {e.place_name && (
                      <span className="inline-flex items-center gap-1">
                        <MapPin size={14} aria-hidden="true" />
                        {e.place_name}
                      </span>
                    )}
                    <span className="inline-flex items-center gap-1">
                      <TypeIcon size={14} aria-hidden="true" />
                      {eventTypeLabel(e.event_type)}
                    </span>
                  </span>
                </td>
                <td className={td}>
                  <AssessmentText assessment={e.assessment} />
                </td>
                <td className={`${td} ${wide}`}>
                  {supporting + ev.contradicts + ev.related === 0 ? (
                    <span className="text-muted">No evidence yet</span>
                  ) : (
                    <span className="flex flex-col gap-0.5 text-muted">
                      <span className="inline-flex items-center gap-1.5">
                        <Paperclip size={14} aria-hidden="true" />
                        {supporting} supporting
                        {ev.contradicts > 0 && (
                          <span className="text-critical">, {ev.contradicts} contradicting</span>
                        )}
                      </span>
                      {ev.reporters > 0 && (
                        <span className="inline-flex items-center gap-1.5">
                          <UserRound size={14} aria-hidden="true" />
                          {ev.reporters} {ev.reporters === 1 ? "field worker" : "field workers"}
                        </span>
                      )}
                      {ev.signals > 0 && (
                        <span className="inline-flex items-center gap-1.5">
                          <RadioTower size={14} aria-hidden="true" />
                          {ev.signals} {ev.signals === 1 ? "public signal" : "public signals"}
                        </span>
                      )}
                    </span>
                  )}
                </td>
                <td className={`${td} ${wide}`}>
                  <StatusText status={e.status} />
                </td>
                <td className={`${td} ${wide} whitespace-nowrap text-muted`}>
                  <span className="inline-flex items-center gap-1.5">
                    <CalendarDays size={15} aria-hidden="true" />
                    {formatDhaka(e.started_at)}
                  </span>
                </td>
                <td className={`${td} w-12`}>
                  <RowOpen href={`/events/${e.id}`} label={e.title} />
                </td>
              </tr>
            );
          })}
        </DataTable>

        {data.total > PAGE_SIZE && (
          <Pager
            page={page}
            lastPage={lastPage}
            total={data.total}
            noun="events"
            newer={page > 1 ? href({ ...current, page: String(page - 1) }) : null}
            older={page < lastPage ? href({ ...current, page: String(page + 1) }) : null}
          />
        )}
      </PageBody>
    </>
  );
}
