import { Camera, Plus } from "lucide-react";
import Link from "next/link";

import { DataTable, EmptyState, rowCls, td, th, wide } from "@/components/data-table";
import { FilterBar } from "@/components/filter-bar";
import { buttonOnBand, PageBand, PageBody, StatTile, StatTiles } from "@/components/page-header";
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
  type Overview,
} from "@/lib/types";

export const metadata = { title: "Field reports" };

const PAGE_SIZE = 25;

type Params = { flagged?: string; q?: string; page?: string };

function href(p: Params): string {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(p)) if (v) params.set(k, v);
  const query = params.toString();
  return query ? `/field-reports?${query}` : "/field-reports";
}

const STATUS_LABEL: Record<string, string> = {
  submitted: "New",
  reviewed: "Reviewed",
  dismissed: "Dismissed",
};

export default async function FieldReportsPage({
  searchParams,
}: {
  searchParams: Promise<Params>;
}) {
  const user = await requireRole(...REPORT_READERS);
  const params = await searchParams;
  // Integrity flags are for reviewers; field workers see their reports without them.
  const reviewer = REPORT_REVIEWERS.includes(user.role);
  const flagged = reviewer && params.flagged === "1";
  const q = (params.q ?? "").trim().slice(0, 100);
  const page = Math.max(1, Number.parseInt(params.page ?? "1", 10) || 1);

  const query = new URLSearchParams({
    limit: String(PAGE_SIZE),
    offset: String((page - 1) * PAGE_SIZE),
  });
  if (flagged) query.set("flagged", "true");
  if (q) query.set("q", q);
  const [data, all, overview] = await Promise.all([
    api<FieldReportPage>(`/field-reports?${query}`),
    api<FieldReportPage>("/field-reports?limit=1"),
    api<Overview>("/overview"),
  ]);

  const ownOnly = user.role === "field_worker";
  const canSubmit = REPORT_SUBMITTERS.includes(user.role);
  const lastPage = Math.max(1, Math.ceil(data.total / PAGE_SIZE));
  const current: Params = { flagged: flagged ? "1" : "", q };

  return (
    <>
      <PageBand
        title={ownOnly ? "Your field reports" : "Field reports"}
        description={
          ownOnly
            ? "What you have reported, newest first. Analysts see each one as soon as it arrives."
            : "What field workers saw, newest first. Flags are prompts to look closer, not verdicts."
        }
        actions={
          canSubmit && (
            <Link href="/field-reports/new" className={buttonOnBand}>
              <Plus size={17} strokeWidth={2.25} aria-hidden="true" />
              New report
            </Link>
          )
        }
      />
      <PageBody>
        <StatTiles>
          <StatTile
            value={overview.reports_24h}
            label="Last 24 hours"
            note={ownOnly ? "Reports you sent" : "Reports observed"}
            tone="green"
          />
          {reviewer ? (
            <>
              <StatTile
                value={overview.flagged_24h ?? 0}
                label="Flagged"
                note="In the last 24 hours"
                tone="red"
                href={href({ flagged: "1" })}
              />
              <StatTile
                value={overview.unreviewed_reports ?? 0}
                label="To review"
                note="Not yet placed against an event"
                tone="amber"
                href="/review"
              />
            </>
          ) : null}
          <StatTile
            value={all.total}
            label={ownOnly ? "All your reports" : "All reports"}
            note="Since the start"
            tone="forest"
          />
        </StatTiles>

        <FilterBar
          action="/field-reports"
          search={{ name: "q", value: q, placeholder: "Search report text or place" }}
          selects={
            reviewer
              ? [
                  {
                    name: "flagged",
                    label: "Show",
                    value: flagged ? "1" : "",
                    options: [
                      { value: "", label: "All reports" },
                      { value: "1", label: "Flagged only" },
                    ],
                  },
                ]
              : []
          }
        />

        <DataTable
          head={
            <tr>
              <th scope="col" className={th}>
                Seen at
              </th>
              <th scope="col" className={th}>
                Report
              </th>
              {!ownOnly && (
                <th scope="col" className={`${th} ${wide}`}>
                  Reported by
                </th>
              )}
              <th scope="col" className={`${th} ${wide}`}>
                Photos
              </th>
              {reviewer && (
                <th scope="col" className={th}>
                  Flags
                </th>
              )}
              <th scope="col" className={th}>
                Status
              </th>
            </tr>
          }
          empty={
            data.items.length === 0 ? (
              <EmptyState>
                {flagged || q
                  ? "No reports match. Clear the filters to see more."
                  : canSubmit
                    ? "No reports yet. Use New report to send the first one."
                    : "No reports yet."}
              </EmptyState>
            ) : undefined
          }
        >
          {data.items.map((r) => (
            <tr key={r.id} className={rowCls}>
              <td className={`${td} whitespace-nowrap text-muted`}>{formatDhaka(r.observed_at)}</td>
              <td className={`${td} max-w-md`}>
                <Link
                  href={`/field-reports/${r.id}`}
                  className="line-clamp-2 font-semibold text-ink hover:text-brand hover:underline"
                >
                  {r.text}
                </Link>
                <span className="mt-0.5 flex flex-wrap gap-x-3 text-muted">
                  <span>{eventTypeLabel(r.event_type)}</span>
                  {r.place_name && <span>{r.place_name}</span>}
                </span>
              </td>
              {!ownOnly && <td className={`${td} ${wide}`}>{r.reporter.full_name}</td>}
              <td className={`${td} ${wide}`}>
                {r.media.length > 0 ? (
                  <span className="inline-flex items-center gap-1 text-muted">
                    <Camera size={14} strokeWidth={1.75} aria-hidden="true" />
                    {r.media.length}
                  </span>
                ) : (
                  <span className="text-muted">None</span>
                )}
              </td>
              {reviewer && (
                <td className={td}>
                  <span className="flex flex-wrap gap-1.5 text-xs">
                    {r.integrity_flags.length === 0 && <span className="text-muted">None</span>}
                    {r.integrity_flags.map((f, i) => (
                      <span
                        key={`${f.code}-${i}`}
                        className="rounded bg-critical-soft px-2 py-0.5 font-semibold text-critical"
                      >
                        {flagLabel(f.code)}
                      </span>
                    ))}
                  </span>
                </td>
              )}
              <td className={td}>
                <span
                  className={r.status === "submitted" ? "font-semibold text-alert" : "text-muted"}
                >
                  {STATUS_LABEL[r.status] ?? r.status}
                </span>
              </td>
            </tr>
          ))}
        </DataTable>

        {data.total > PAGE_SIZE && (
          <Pager
            page={page}
            lastPage={lastPage}
            total={data.total}
            noun="reports"
            newer={page > 1 ? href({ ...current, page: String(page - 1) }) : null}
            older={page < lastPage ? href({ ...current, page: String(page + 1) }) : null}
          />
        )}
      </PageBody>
    </>
  );
}
