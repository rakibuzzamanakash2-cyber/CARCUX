import Link from "next/link";

import { api } from "@/lib/api";
import { requireRole } from "@/lib/dal";
import { eventTypeLabel } from "@/lib/event-types";
import { flagLabel, formatDhaka } from "@/lib/format";
import {
  REPORT_READERS,
  REPORT_REVIEWERS,
  REPORT_SUBMITTERS,
  type FieldReportPage,
} from "@/lib/types";

export const metadata = { title: "Field reports" };

const PAGE_SIZE = 25;

function pageHref(flagged: boolean, page: number): string {
  const params = new URLSearchParams();
  if (flagged) params.set("flagged", "1");
  if (page > 1) params.set("page", String(page));
  const query = params.toString();
  return query ? `/field-reports?${query}` : "/field-reports";
}

export default async function FieldReportsPage({
  searchParams,
}: {
  searchParams: Promise<{ flagged?: string; page?: string }>;
}) {
  const user = await requireRole(...REPORT_READERS);
  const params = await searchParams;
  // Integrity flags are for reviewers; field workers see their reports without them.
  const reviewer = REPORT_REVIEWERS.includes(user.role);
  const flagged = reviewer && params.flagged === "1";
  const page = Math.max(1, Number.parseInt(params.page ?? "1", 10) || 1);

  const query = new URLSearchParams({
    limit: String(PAGE_SIZE),
    offset: String((page - 1) * PAGE_SIZE),
  });
  if (flagged) query.set("flagged", "true");
  const data = await api<FieldReportPage>(`/field-reports?${query}`);

  const ownOnly = user.role === "field_worker";
  const canSubmit = REPORT_SUBMITTERS.includes(user.role);
  const lastPage = Math.max(1, Math.ceil(data.total / PAGE_SIZE));

  return (
    <div className="flex flex-col gap-8">
      <section className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="display mb-3 text-4xl">
            {ownOnly ? "Your field reports" : "Field reports"}
          </h1>
          <p className="max-w-2xl text-steel">
            {ownOnly
              ? "What you have reported, newest first. Analysts see these as soon as they arrive."
              : "What field workers saw, newest first. Flags are prompts to look closer, not verdicts."}
          </p>
        </div>
        {canSubmit && (
          <Link
            href="/field-reports/new"
            className="inline-flex h-11 shrink-0 items-center justify-center rounded-sm bg-bone px-5 font-semibold text-ground transition-colors hover:bg-white"
          >
            New report
          </Link>
        )}
      </section>

      {reviewer && (
        <nav aria-label="Filter" className="flex gap-1 border-b border-line text-sm">
          {[
            { label: "All", on: !flagged, href: pageHref(false, 1) },
            { label: "Flagged", on: flagged, href: pageHref(true, 1) },
          ].map((tab) => (
            <Link
              key={tab.label}
              href={tab.href}
              aria-current={tab.on ? "page" : undefined}
              className={`-mb-px border-b-2 px-3 py-2 transition-colors ${
                tab.on ? "border-signal text-bone" : "border-transparent text-steel hover:text-bone"
              }`}
            >
              {tab.label}
            </Link>
          ))}
        </nav>
      )}

      {data.items.length === 0 ? (
        <p className="text-steel">
          {flagged
            ? "No flagged reports."
            : canSubmit
              ? "No reports yet. Use New report to send the first one."
              : "No reports yet."}
        </p>
      ) : (
        <ul className="flex flex-col divide-y divide-line border-y border-line">
          {data.items.map((r) => {
            const flags = reviewer ? r.integrity_flags : [];
            return (
              <li key={r.id}>
                <Link
                  href={`/field-reports/${r.id}`}
                  className="grid gap-2 py-4 transition-colors hover:bg-panel sm:grid-cols-[10rem_1fr_auto] sm:gap-6 sm:px-2"
                >
                  <div className="text-sm text-steel">
                    <p>{formatDhaka(r.observed_at)}</p>
                    {!ownOnly && <p className="truncate">{r.reporter.full_name}</p>}
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm text-steel">
                      {eventTypeLabel(r.event_type)}
                      {r.place_name && <span> · {r.place_name}</span>}
                    </p>
                    <p className="line-clamp-2">{r.text}</p>
                  </div>
                  <div className="flex flex-wrap items-start gap-2 text-xs sm:justify-end">
                    {r.media.length > 0 && (
                      <span className="rounded-sm border border-line px-2 py-1 text-steel">
                        {r.media.length} {r.media.length === 1 ? "photo" : "photos"}
                      </span>
                    )}
                    {flags.map((f, i) => (
                      <span
                        key={`${f.code}-${i}`}
                        className="rounded-sm bg-signal-soft px-2 py-1 text-bone"
                      >
                        {flagLabel(f.code)}
                      </span>
                    ))}
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      )}

      {data.total > PAGE_SIZE && (
        <nav aria-label="Pages" className="flex items-center gap-4 text-sm">
          {page > 1 ? (
            <Link href={pageHref(flagged, page - 1)} className="text-steel hover:text-bone">
              ← Newer
            </Link>
          ) : (
            <span className="text-steel/40">← Newer</span>
          )}
          <span className="text-steel">
            Page {page} of {lastPage} · {data.total} reports
          </span>
          {page < lastPage ? (
            <Link href={pageHref(flagged, page + 1)} className="text-steel hover:text-bone">
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
