import { Plus } from "lucide-react";
import Link from "next/link";

import {
  AssessmentText,
  EvidenceSummary,
  PriorityBadge,
  StatusText,
} from "@/components/event-badges";
import { buttonPrimary, PageHeader } from "@/components/page-header";
import { Pager } from "@/components/pager";
import { api } from "@/lib/api";
import { verifySession } from "@/lib/dal";
import { eventTypeLabel } from "@/lib/event-types";
import { FAMILIES } from "@/lib/events";
import { formatDhaka } from "@/lib/format";
import { REPORT_REVIEWERS, type EventPage, type EventStatus } from "@/lib/types";

export const metadata = { title: "Events" };

const PAGE_SIZE = 25;

const VIEWS: { key: string; label: string; statuses: EventStatus[] }[] = [
  { key: "open", label: "Open", statuses: ["active", "monitoring"] },
  { key: "resolved", label: "Resolved", statuses: ["resolved"] },
  { key: "dismissed", label: "Dismissed", statuses: ["dismissed"] },
  { key: "all", label: "All", statuses: [] },
];

function href(view: string, family: string, page = 1): string {
  const params = new URLSearchParams();
  if (view !== "open") params.set("view", view);
  if (family) params.set("family", family);
  if (page > 1) params.set("page", String(page));
  const query = params.toString();
  return query ? `/events?${query}` : "/events";
}

export default async function EventsPage({
  searchParams,
}: {
  searchParams: Promise<{ view?: string; family?: string; page?: string }>;
}) {
  const user = await verifySession();
  const params = await searchParams;
  const view = VIEWS.find((v) => v.key === params.view) ?? VIEWS[0];
  const family = FAMILIES.some((f) => f.value === params.family) ? params.family! : "";
  const page = Math.max(1, Number.parseInt(params.page ?? "1", 10) || 1);

  const query = new URLSearchParams({
    limit: String(PAGE_SIZE),
    offset: String((page - 1) * PAGE_SIZE),
  });
  for (const s of view.statuses) query.append("status", s);
  if (family) query.set("family", family);
  const data = await api<EventPage>(`/events?${query}`);

  const reviewer = REPORT_REVIEWERS.includes(user.role);
  const lastPage = Math.max(1, Math.ceil(data.total / PAGE_SIZE));

  const tabCls = (on: boolean) =>
    `rounded-md px-3 py-1.5 text-sm transition-colors ${
      on ? "bg-panel-2 text-ink" : "text-muted hover:text-ink"
    }`;

  return (
    <>
      <PageHeader
        title="Events"
        description="Each situation being tracked, with the analysts' assessment and the evidence behind it."
        actions={
          reviewer && (
            <Link href="/events/new" className={buttonPrimary}>
              <Plus size={17} strokeWidth={2.25} aria-hidden="true" />
              New event
            </Link>
          )
        }
      />

      <div className="rounded-lg border border-line bg-panel">
        <div className="flex flex-col gap-2 border-b border-line p-2 sm:flex-row sm:items-center sm:justify-between">
          <nav aria-label="Status" className="flex gap-1">
            {VIEWS.map((v) => (
              <Link
                key={v.key}
                href={href(v.key, family)}
                aria-current={v.key === view.key ? "page" : undefined}
                className={tabCls(v.key === view.key)}
              >
                {v.label}
              </Link>
            ))}
          </nav>
          <nav aria-label="Kind of event" className="flex flex-wrap gap-1">
            {[{ value: "", label: "Every kind" }, ...FAMILIES].map((f) => (
              <Link
                key={f.value}
                href={href(view.key, f.value)}
                aria-current={f.value === family ? "page" : undefined}
                className={tabCls(f.value === family)}
              >
                {f.label}
              </Link>
            ))}
          </nav>
        </div>

        {data.items.length === 0 ? (
          <p className="p-5 text-muted">
            {view.key === "open"
              ? reviewer
                ? "No open events. Create one from a field report, or with New event."
                : "No open events."
              : "No events here."}
          </p>
        ) : (
          <ul className="divide-y divide-line">
            {data.items.map((e) => (
              <li key={e.id}>
                <Link
                  href={`/events/${e.id}`}
                  className="grid gap-2 px-4 py-3 transition-colors hover:bg-panel-2 md:grid-cols-[6rem_1fr_11rem_9rem] md:items-center md:gap-4"
                >
                  <span>
                    <PriorityBadge priority={e.priority} />
                  </span>
                  <span className="min-w-0">
                    <span className="display block truncate text-lg">{e.title}</span>
                    <span className="flex flex-wrap gap-x-3 text-sm text-muted">
                      <span>{eventTypeLabel(e.event_type)}</span>
                      {e.place_name && <span>{e.place_name}</span>}
                      <EvidenceSummary counts={e.evidence_counts} />
                    </span>
                  </span>
                  <span className="text-sm">
                    <AssessmentText assessment={e.assessment} />
                  </span>
                  <span className="text-sm text-muted md:text-right">
                    <StatusText status={e.status} />
                    <span className="block">{formatDhaka(e.started_at)}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>

      {data.total > PAGE_SIZE && (
        <Pager
          page={page}
          lastPage={lastPage}
          total={data.total}
          noun="events"
          newer={page > 1 ? href(view.key, family, page - 1) : null}
          older={page < lastPage ? href(view.key, family, page + 1) : null}
        />
      )}
    </>
  );
}
