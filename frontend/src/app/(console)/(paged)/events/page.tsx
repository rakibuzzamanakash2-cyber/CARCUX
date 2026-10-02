import Link from "next/link";

import {
  AssessmentText,
  EvidenceSummary,
  PriorityBadge,
  StatusText,
} from "@/components/event-badges";
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

  return (
    <div className="flex flex-col gap-8">
      <section className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="display mb-3 text-4xl">Events</h1>
          <p className="max-w-2xl text-steel">
            Each situation CARCUX is tracking, with the assessment analysts have reached and the
            evidence behind it.
          </p>
        </div>
        {reviewer && (
          <Link
            href="/events/new"
            className="inline-flex h-11 shrink-0 items-center justify-center rounded-sm bg-bone px-5 font-semibold text-ground transition-colors hover:bg-white"
          >
            New event
          </Link>
        )}
      </section>

      <div className="flex flex-col gap-3 border-b border-line sm:flex-row sm:items-end sm:justify-between">
        <nav aria-label="Status" className="flex gap-1 text-sm">
          {VIEWS.map((v) => (
            <Link
              key={v.key}
              href={href(v.key, family)}
              aria-current={v.key === view.key ? "page" : undefined}
              className={`-mb-px border-b-2 px-3 py-2 transition-colors ${
                v.key === view.key
                  ? "border-signal text-bone"
                  : "border-transparent text-steel hover:text-bone"
              }`}
            >
              {v.label}
            </Link>
          ))}
        </nav>
        <nav aria-label="Kind of event" className="flex flex-wrap gap-x-4 gap-y-1 pb-2 text-sm">
          {[{ value: "", label: "Every kind" }, ...FAMILIES].map((f) => (
            <Link
              key={f.value}
              href={href(view.key, f.value)}
              aria-current={f.value === family ? "page" : undefined}
              className={f.value === family ? "text-bone" : "text-steel hover:text-bone"}
            >
              {f.label}
            </Link>
          ))}
        </nav>
      </div>

      {data.items.length === 0 ? (
        <p className="text-steel">
          {view.key === "open"
            ? reviewer
              ? "No open events. Create one from a field report, or with New event."
              : "No open events."
            : "No events here."}
        </p>
      ) : (
        <ul className="flex flex-col divide-y divide-line border-y border-line">
          {data.items.map((e) => (
            <li key={e.id}>
              <Link
                href={`/events/${e.id}`}
                className="grid gap-2 py-4 transition-colors hover:bg-panel sm:grid-cols-[1fr_auto] sm:gap-6 sm:px-2"
              >
                <div className="min-w-0">
                  <p className="text-sm text-steel">
                    {eventTypeLabel(e.event_type)}
                    {e.place_name && <span> · {e.place_name}</span>}
                    <span> · since {formatDhaka(e.started_at)}</span>
                  </p>
                  <p className="text-lg">{e.title}</p>
                  <p className="text-sm">
                    <EvidenceSummary counts={e.evidence_counts} />
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-3 text-sm sm:flex-col sm:items-end sm:gap-1.5">
                  <PriorityBadge priority={e.priority} />
                  <AssessmentText assessment={e.assessment} />
                  <StatusText status={e.status} />
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}

      {data.total > PAGE_SIZE && (
        <nav aria-label="Pages" className="flex items-center gap-4 text-sm">
          {page > 1 ? (
            <Link href={href(view.key, family, page - 1)} className="text-steel hover:text-bone">
              ← Newer
            </Link>
          ) : (
            <span className="text-steel/40">← Newer</span>
          )}
          <span className="text-steel">
            Page {page} of {lastPage} · {data.total} events
          </span>
          {page < lastPage ? (
            <Link href={href(view.key, family, page + 1)} className="text-steel hover:text-bone">
              Older →
            </Link>
          ) : (
            <span className="text-steel/40">Older →</span>
          )}
        </nav>
      )}
    </div>
  );
}
