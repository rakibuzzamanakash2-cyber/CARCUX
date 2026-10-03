import {
  CalendarDays,
  Camera,
  ClipboardList,
  Eye,
  FileText,
  Flag,
  ImageIcon,
  Plus,
} from "lucide-react";
import Link from "next/link";

import {
  DataTable,
  EmptyState,
  Initials,
  Pill,
  RowOpen,
  rowCls,
  td,
  th,
  wide,
} from "@/components/data-table";
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
        scene="paddy"
        icon={ClipboardList}
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
            icon={ClipboardList}
            value={overview.reports_24h}
            label="Last 24 hours"
            note={ownOnly ? "Reports you sent" : "Reports observed"}
            tone="green"
          />
          {reviewer ? (
            <>
              <StatTile
                icon={Flag}
                value={overview.flagged_24h ?? 0}
                label="Flagged"
                note="In the last 24 hours"
                tone="red"
                href={href({ flagged: "1" })}
              />
              <StatTile
                icon={Eye}
                value={overview.unreviewed_reports ?? 0}
                label="To review"
                note="Not yet placed against an event"
                tone="amber"
                href="/review"
              />
            </>
          ) : null}
          <StatTile
            icon={FileText}
            value={all.total}
            label={ownOnly ? "All your reports" : "All reports"}
            note="Since the start"
            tone="blue"
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
              <th scope="col" className={th}>
                <span className="sr-only">Open</span>
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
              <td className={`${td} whitespace-nowrap text-muted`}>
                <span className="inline-flex items-center gap-2">
                  <CalendarDays size={16} aria-hidden="true" className="text-brand" />
                  {formatDhaka(r.observed_at)}
                </span>
              </td>
              <td className={`${td} max-w-md`}>
                <Link
                  href={`/field-reports/${r.id}`}
                  className="line-clamp-2 text-[15px] font-semibold text-ink hover:text-brand hover:underline"
                >
                  {r.text}
                </Link>
                <span className="mt-0.5 block text-muted italic">
                  {eventTypeLabel(r.event_type)}
                  {r.place_name && <span className="not-italic">, {r.place_name}</span>}
                </span>
              </td>
              {!ownOnly && (
                <td className={`${td} ${wide}`}>
                  <span className="flex items-center gap-2">
                    <Initials name={r.reporter.full_name} />
                    {r.reporter.full_name}
                  </span>
                </td>
              )}
              <td className={`${td} ${wide}`}>
                <span className="inline-flex items-center gap-1.5 text-muted">
                  {r.media.length > 0 ? (
                    <ImageIcon size={16} aria-hidden="true" />
                  ) : (
                    <Camera size={16} aria-hidden="true" />
                  )}
                  {r.media.length > 0 ? r.media.length : "None"}
                </span>
              </td>
              {reviewer && (
                <td className={td}>
                  <span className="flex flex-wrap gap-1.5">
                    {r.integrity_flags.length === 0 ? (
                      <Pill tone="grey">
                        <Flag size={13} aria-hidden="true" />
                        None
                      </Pill>
                    ) : (
                      r.integrity_flags.map((f, i) => (
                        <Pill key={`${f.code}-${i}`} tone="red">
                          <Flag size={13} aria-hidden="true" />
                          {flagLabel(f.code)}
                        </Pill>
                      ))
                    )}
                  </span>
                </td>
              )}
              <td className={td}>
                <Pill
                  tone={
                    r.status === "submitted" ? "amber" : r.status === "reviewed" ? "green" : "grey"
                  }
                >
                  {STATUS_LABEL[r.status] ?? r.status}
                </Pill>
              </td>
              <td className={`${td} w-12`}>
                <RowOpen href={`/field-reports/${r.id}`} label="report" />
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
