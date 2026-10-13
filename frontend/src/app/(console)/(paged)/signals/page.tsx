import {
  AlertTriangle,
  Inbox,
  Landmark,
  Newspaper,
  PenLine,
  RadioTower,
  Rss,
  Siren,
} from "lucide-react";
import Link from "next/link";

import { DataTable, EmptyState, RowOpen, rowCls, td, th, wide } from "@/components/data-table";
import { FilterBar } from "@/components/filter-bar";
import { buttonOnBand, PageBand, PageBody, StatTile, StatTiles } from "@/components/page-header";
import { Pager } from "@/components/pager";
import { SeverityPill, SignalStatusPill } from "@/components/signal-bits";
import { api } from "@/lib/api";
import { verifySession } from "@/lib/dal";
import { eventTypeIcon } from "@/lib/event-icons";
import { eventTypeLabel } from "@/lib/event-types";
import { FAMILIES } from "@/lib/events";
import { formatDhaka } from "@/lib/format";
import { ADAPTER, SIGNAL_STATUSES } from "@/lib/signals";
import { REPORT_REVIEWERS, type SignalPage, type Source } from "@/lib/types";

export const metadata = { title: "Public signals" };

const PAGE_SIZE = 25;

type Params = {
  q?: string;
  source?: string;
  family?: string;
  status?: string;
  page?: string;
};

function href(p: Params): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(p)) if (v) q.set(k, v);
  const s = q.toString();
  return s ? `/signals?${s}` : "/signals";
}

function since(hours: number): string {
  return new Date(Date.now() - hours * 3_600_000).toISOString();
}

export default async function SignalsPage({ searchParams }: { searchParams: Promise<Params> }) {
  const user = await verifySession();
  const reviewer = REPORT_REVIEWERS.includes(user.role);
  const params = await searchParams;
  const page = Math.max(1, Number.parseInt(params.page ?? "1", 10) || 1);
  const q = (params.q ?? "").trim();
  const family = FAMILIES.some((f) => f.value === params.family) ? params.family! : "";
  const status = SIGNAL_STATUSES.some((s) => s.value === params.status) ? params.status! : "";

  const sources = reviewer ? await api<Source[]>("/sources") : [];
  const source = sources.some((s) => s.id === params.source) ? params.source! : "";

  const query = new URLSearchParams({
    limit: String(PAGE_SIZE),
    offset: String((page - 1) * PAGE_SIZE),
  });
  if (q) query.set("q", q);
  if (family) query.set("family", family);
  if (status) query.set("status", status);
  if (source) query.set("source", source);

  const [data, today, waiting] = await Promise.all([
    api<SignalPage>(`/signals?${query}`),
    api<SignalPage>(`/signals?limit=200&since=${encodeURIComponent(since(24))}`),
    reviewer ? api<SignalPage>("/signals?status=new&limit=1") : Promise.resolve(null),
  ]);
  const severeToday = today.items.filter((s) => s.severity === "severe").length;
  const officialToday = today.items.filter((s) => s.source.source_type === "public_record").length;
  // Feeds that are read automatically; manual sources have nothing to fail.
  const feeds = sources.filter((s) => s.enabled && s.adapter !== "manual");
  const failing = feeds.filter((s) => s.last_error).length;
  const lastPage = Math.max(1, Math.ceil(data.total / PAGE_SIZE));
  const current: Params = { q, source, family, status };

  return (
    <>
      <PageBand
        scene="padma"
        icon={RadioTower}
        title="Public signals"
        description="Disaster alerts, official bulletins and news about Bangladesh, collected automatically or entered by analysts. Each can be linked to an event as evidence."
        actions={
          reviewer && (
            <Link href="/signals/new" className={buttonOnBand}>
              <PenLine size={17} strokeWidth={2.25} aria-hidden="true" />
              Enter a bulletin
            </Link>
          )
        }
      />
      <PageBody>
        <StatTiles>
          <StatTile
            icon={RadioTower}
            value={today.total}
            label="Last 24 hours"
            note="Published in the last day"
            tone="blue"
          />
          <StatTile
            icon={Siren}
            value={severeToday}
            label="Severe alerts"
            note="Red alerts in the last day"
            tone="red"
          />
          {waiting ? (
            <StatTile
              icon={Inbox}
              value={waiting.total}
              label="New"
              note="Not yet looked at"
              tone="amber"
              href={href({ status: "new" })}
            />
          ) : (
            <StatTile
              icon={Landmark}
              value={officialToday}
              label="Official alerts"
              note="Alerts and bulletins, last day"
              tone="amber"
            />
          )}
          {reviewer ? (
            <StatTile
              icon={failing ? AlertTriangle : Rss}
              value={`${feeds.length - failing} of ${feeds.length}`}
              label="Feeds working"
              note={failing ? `${failing} could not be read last time` : "All read normally"}
              tone={failing ? "red" : "green"}
              href="/sources"
            />
          ) : (
            <StatTile
              icon={Newspaper}
              value={today.total - officialToday}
              label="News items"
              note="Placed in Bangladesh, last day"
              tone="green"
            />
          )}
        </StatTiles>

        <FilterBar
          action="/signals"
          search={{
            name: "q",
            value: q,
            placeholder: "Words in the headline, text or place",
          }}
          selects={[
            ...(reviewer
              ? [
                  {
                    name: "source",
                    label: "Source",
                    value: source,
                    options: [
                      { value: "", label: "Every source" },
                      ...sources.map((s) => ({ value: s.id, label: s.name })),
                    ],
                  },
                ]
              : []),
            {
              name: "family",
              label: "Kind",
              value: family,
              options: [
                { value: "", label: "Every kind" },
                ...FAMILIES.map((f) => ({ value: f.value, label: f.label })),
              ],
            },
            {
              name: "status",
              label: "Status",
              value: status,
              options: [{ value: "", label: "Any status" }, ...SIGNAL_STATUSES],
            },
          ]}
        />

        <DataTable
          head={
            <tr>
              <th scope="col" className={th}>
                Signal
              </th>
              <th scope="col" className={th}>
                Source
              </th>
              <th scope="col" className={`${th} ${wide}`}>
                Severity
              </th>
              <th scope="col" className={`${th} ${wide}`}>
                Status
              </th>
              <th scope="col" className={`${th} ${wide}`}>
                Published
              </th>
              <th scope="col" className={th}>
                <span className="sr-only">Open</span>
              </th>
            </tr>
          }
          empty={
            data.items.length === 0 ? (
              <EmptyState>
                {q || family || status || source
                  ? "No signals match these filters."
                  : "No signals yet. Sources are read every half hour; an admin can read one now on the Sources page."}
              </EmptyState>
            ) : undefined
          }
        >
          {data.items.map((s) => {
            const TypeIcon = eventTypeIcon(s.event_type);
            const { icon: SourceIcon } = ADAPTER[s.source.adapter];
            return (
              <tr key={s.id} className={rowCls}>
                <td className={td}>
                  <Link
                    href={`/signals/${s.id}`}
                    className="text-[15px] font-semibold text-ink hover:text-brand hover:underline"
                  >
                    {s.title}
                  </Link>
                  <span className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-muted italic">
                    {s.event_type && (
                      <span className="inline-flex items-center gap-1 not-italic">
                        <TypeIcon size={14} aria-hidden="true" />
                        {eventTypeLabel(s.event_type)}
                      </span>
                    )}
                    {s.place_name && <span>{s.place_name}</span>}
                  </span>
                </td>
                <td className={td}>
                  <span className="inline-flex items-center gap-2">
                    <SourceIcon size={16} aria-hidden="true" className="shrink-0 text-brand" />
                    {s.source.name}
                  </span>
                </td>
                <td className={`${td} ${wide}`}>
                  <SeverityPill severity={s.severity} />
                </td>
                <td className={`${td} ${wide}`}>
                  <SignalStatusPill status={s.status} />
                </td>
                <td className={`${td} ${wide} whitespace-nowrap text-muted`}>
                  {formatDhaka(s.published_at)}
                </td>
                <td className={td}>
                  <RowOpen href={`/signals/${s.id}`} label={`Open signal: ${s.title}`} />
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
            noun="signals"
            newer={page > 1 ? href({ ...current, page: String(page - 1) }) : null}
            older={page < lastPage ? href({ ...current, page: String(page + 1) }) : null}
          />
        )}
      </PageBody>
    </>
  );
}
