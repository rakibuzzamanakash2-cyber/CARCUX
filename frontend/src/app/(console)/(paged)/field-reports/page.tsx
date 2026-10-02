import { Camera, Plus } from "lucide-react";
import Link from "next/link";

import { buttonPrimary, PageHeader } from "@/components/page-header";
import { Pager } from "@/components/pager";

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

  const tabCls = (on: boolean) =>
    `rounded-md px-3 py-1.5 text-sm transition-colors ${
      on ? "bg-panel-2 text-ink" : "text-muted hover:text-ink"
    }`;

  return (
    <>
      <PageHeader
        title={ownOnly ? "Your field reports" : "Field reports"}
        description={
          ownOnly
            ? "What you have reported, newest first. Analysts see each one as soon as it arrives."
            : "What field workers saw, newest first. Flags are prompts to look closer, not verdicts."
        }
        actions={
          canSubmit && (
            <Link href="/field-reports/new" className={buttonPrimary}>
              <Plus size={17} strokeWidth={2.25} aria-hidden="true" />
              New report
            </Link>
          )
        }
      />

      <div className="rounded-lg border border-line bg-panel">
        {reviewer && (
          <nav aria-label="Filter" className="flex gap-1 border-b border-line p-2">
            {[
              { label: "All", on: !flagged, href: pageHref(false, 1) },
              { label: "Flagged", on: flagged, href: pageHref(true, 1) },
            ].map((tab) => (
              <Link
                key={tab.label}
                href={tab.href}
                aria-current={tab.on ? "page" : undefined}
                className={tabCls(tab.on)}
              >
                {tab.label}
              </Link>
            ))}
          </nav>
        )}

        {data.items.length === 0 ? (
          <p className="p-5 text-muted">
            {flagged
              ? "No flagged reports."
              : canSubmit
                ? "No reports yet. Use New report to send the first one."
                : "No reports yet."}
          </p>
        ) : (
          <ul className="divide-y divide-line">
            {data.items.map((r) => {
              const flags = reviewer ? r.integrity_flags : [];
              return (
                <li key={r.id}>
                  <Link
                    href={`/field-reports/${r.id}`}
                    className="grid gap-2 px-4 py-3 transition-colors hover:bg-panel-2 md:grid-cols-[9rem_1fr_auto] md:items-center md:gap-4"
                  >
                    <span className="text-sm text-muted">
                      <span className="block text-ink">{formatDhaka(r.observed_at)}</span>
                      {!ownOnly && <span className="block truncate">{r.reporter.full_name}</span>}
                    </span>
                    <span className="min-w-0">
                      <span className="flex flex-wrap gap-x-3 text-sm text-muted">
                        <span>{eventTypeLabel(r.event_type)}</span>
                        {r.place_name && <span>{r.place_name}</span>}
                      </span>
                      <span className="line-clamp-2">{r.text}</span>
                    </span>
                    <span className="flex flex-wrap items-center gap-2 text-xs md:justify-end">
                      {r.media.length > 0 && (
                        <span className="inline-flex items-center gap-1 rounded bg-panel-2 px-2 py-1 text-muted">
                          <Camera size={13} strokeWidth={1.75} aria-hidden="true" />
                          {r.media.length}
                          <span className="sr-only">
                            {" "}
                            {r.media.length === 1 ? "photo" : "photos"}
                          </span>
                        </span>
                      )}
                      {flags.map((f, i) => (
                        <span
                          key={`${f.code}-${i}`}
                          className="rounded bg-critical-soft px-2 py-1 text-ink ring-1 ring-critical/40"
                        >
                          {flagLabel(f.code)}
                        </span>
                      ))}
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {data.total > PAGE_SIZE && (
        <Pager
          page={page}
          lastPage={lastPage}
          total={data.total}
          noun="reports"
          newer={page > 1 ? pageHref(flagged, page - 1) : null}
          older={page < lastPage ? pageHref(flagged, page + 1) : null}
        />
      )}
    </>
  );
}
