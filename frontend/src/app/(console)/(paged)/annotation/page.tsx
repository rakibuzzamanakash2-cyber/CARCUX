import { BarChart3, CalendarDays, MapPin, Scale, Target, Users2, UserCheck } from "lucide-react";
import Link from "next/link";

import { Pill } from "@/components/data-table";
import { PageBand, PageBody, Panel, StatTile, StatTiles, Tabs } from "@/components/page-header";
import { Pager } from "@/components/pager";
import { SignalSummary } from "@/components/signal-bits";
import { api } from "@/lib/api";
import { requireRole } from "@/lib/dal";
import { eventTypeLabel } from "@/lib/event-types";
import { claimLabel, CONFIDENCE, relationLabel, RELATIONS } from "@/lib/events";
import { flagLabel, formatDhaka } from "@/lib/format";
import {
  JUDGES,
  type AgreementStats,
  type BlindEvent,
  type BlindFieldReport,
  type BlindSignal,
  type Disagreement,
  type QueueItem,
} from "@/lib/types";

import { DecideForm } from "./decide-form";
import { JudgeForm } from "./judge-form";

export const metadata = { title: "Second opinions" };

const PAGE_SIZE = 5;

function num(value: number | null, digits = 2): string {
  return value === null ? "Not yet" : value.toFixed(digits);
}

/** The event as the annotator should judge against it: what, where, when, ground truth.
 * Blind: no link to the event page, whose Evidence tab and counts show the first label. */
function EventBlock({ event, blind = false }: { event: BlindEvent; blind?: boolean }) {
  return (
    <div className="flex flex-col gap-1">
      <p className="text-xs font-bold tracking-wide text-muted uppercase">Event</p>
      {blind ? (
        <p className="text-lg leading-snug font-semibold">{event.title}</p>
      ) : (
        <Link
          href={`/events/${event.id}`}
          className="text-lg leading-snug font-semibold hover:text-brand hover:underline"
        >
          {event.title}
        </Link>
      )}
      <p className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted">
        <span>{eventTypeLabel(event.event_type)}</span>
        {event.place_name && (
          <span className="inline-flex items-center gap-1">
            <MapPin size={14} aria-hidden="true" />
            {event.place_name}
          </span>
        )}
        <span className="inline-flex items-center gap-1">
          <CalendarDays size={14} aria-hidden="true" />
          {formatDhaka(event.started_at)}
          {event.ended_at ? ` to ${formatDhaka(event.ended_at)}` : ", ongoing"}
        </span>
      </p>
      {event.summary && <p className="line-clamp-3 text-sm">{event.summary}</p>}
      <p className="text-sm text-muted">
        Ground truth:{" "}
        {event.occurred === null
          ? "not established yet"
          : event.occurred
            ? `it happened (${event.ground_truth_sources.length} source${event.ground_truth_sources.length === 1 ? "" : "s"})`
            : "it did not happen"}
        {event.ground_truth_note ? `. ${event.ground_truth_note}` : ""}
      </p>
    </div>
  );
}

function ItemBlock({
  report,
  signal,
  blind = false,
}: {
  report: BlindFieldReport | null;
  signal: BlindSignal | null;
  blind?: boolean;
}) {
  if (signal)
    return (
      <div className="flex flex-col gap-1">
        <p className="text-xs font-bold tracking-wide text-muted uppercase">Public signal</p>
        <SignalSummary signal={signal} blind={blind} />
      </div>
    );
  if (!report) return null;
  return (
    <div className="flex flex-col gap-1">
      <p className="text-xs font-bold tracking-wide text-muted uppercase">Field report</p>
      <p className="flex flex-wrap gap-x-4 text-sm text-muted">
        <span>Seen {formatDhaka(report.observed_at)}</span>
        {report.place_name && <span>{report.place_name}</span>}
        {report.media.length > 0 && (
          <span>
            {report.media.length} {report.media.length === 1 ? "photo" : "photos"}
          </span>
        )}
      </p>
      {blind ? (
        <p>{report.text}</p>
      ) : (
        <Link href={`/field-reports/${report.id}`} className="hover:text-brand hover:underline">
          {report.text}
        </Link>
      )}
      {report.integrity_flags.length > 0 && (
        <p className="flex flex-wrap gap-2">
          {report.integrity_flags.map((f, i) => (
            <Pill key={i} tone="red">
              {flagLabel(f.code)}
            </Pill>
          ))}
        </p>
      )}
    </div>
  );
}

export default async function AnnotationPage({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string; page?: string }>;
}) {
  const user = await requireRole(...JUDGES);
  // Annotators see only their queue: agreement figures that change as they judge would
  // tell them whether they agreed with the first label.
  const annotator = user.role === "annotator";
  const params = await searchParams;
  const tab = !annotator && params.tab === "agreement" ? "agreement" : "queue";
  const page = Math.max(1, Number.parseInt(params.page ?? "1", 10) || 1);

  const [queue, stats] = await Promise.all([
    api<{ items: QueueItem[]; total: number }>(
      `/annotation/queue?limit=${PAGE_SIZE}&offset=${(page - 1) * PAGE_SIZE}`,
    ),
    annotator ? null : api<AgreementStats>("/annotation/agreement"),
  ]);
  const disagreements =
    tab === "agreement" ? await api<Disagreement[]>("/annotation/disagreements") : [];
  const lastPage = Math.max(1, Math.ceil(queue.total / PAGE_SIZE));
  const met = stats !== null && stats.kappa !== null && stats.kappa >= stats.target;
  const labels = RELATIONS.map((r) => r.value);

  return (
    <>
      <PageBand
        scene="hills"
        icon={Users2}
        title="Second opinions"
        description="Every link between an item and an event is judged by two annotators, independently. Labels already given are not shown here, so your judgement stays your own."
      />
      <PageBody>
        <StatTiles>
          <StatTile
            icon={UserCheck}
            value={queue.total}
            label="Waiting for you"
            note="Links you have not judged"
            tone="amber"
            href="/annotation"
          />
          {stats && (
            <>
              <StatTile
                icon={Target}
                value={num(stats.kappa)}
                label="Cohen's κ"
                note={`Target ${stats.target.toFixed(2)} or more${stats.kappa === null ? "" : met ? ", met" : ", not met yet"}`}
                tone={stats.kappa === null ? "blue" : met ? "green" : "red"}
                href="/annotation?tab=agreement"
              />
              <StatTile
                icon={BarChart3}
                value={num(stats.alpha)}
                label="Krippendorff's α"
                note={`${stats.items_with_two} of ${stats.items_total} links judged twice`}
                tone="forest"
              />
              <StatTile
                icon={Scale}
                value={stats.open_disagreements}
                label="To decide"
                note="Disagreements without a final label"
                tone={stats.open_disagreements ? "red" : "green"}
                href="/annotation?tab=agreement"
              />
            </>
          )}
        </StatTiles>

        {stats && (
          <Tabs
            active={tab}
            items={[
              {
                key: "queue",
                label: "Judge",
                href: "/annotation",
                icon: UserCheck,
                count: queue.total,
              },
              {
                key: "agreement",
                label: "Agreement",
                href: "/annotation?tab=agreement",
                icon: Scale,
                count: stats.open_disagreements,
              },
            ]}
          />
        )}

        {tab === "queue" &&
          (queue.items.length === 0 ? (
            <Panel>
              <p className="py-8 text-center text-muted">
                Nothing is waiting for your judgement. Links you made yourself count as your first
                judgement.
              </p>
            </Panel>
          ) : (
            <ol className="flex flex-col gap-4" aria-label="Links waiting for your judgement">
              {queue.items.map((q) => (
                <li
                  key={q.evidence_id}
                  className="grid gap-5 rounded-xl border border-line bg-panel p-4 shadow-sm md:p-5 lg:grid-cols-[1fr_26rem]"
                >
                  <div className="flex min-w-0 flex-col gap-4">
                    <EventBlock event={q.event} blind />
                    <div className="border-t border-line pt-4">
                      <ItemBlock report={q.field_report} signal={q.signal} blind />
                    </div>
                  </div>
                  <JudgeForm
                    evidenceId={q.evidence_id}
                    label="What does the item say about this event?"
                  />
                </li>
              ))}
            </ol>
          ))}

        {tab === "queue" && queue.total > PAGE_SIZE && (
          <Pager
            page={page}
            lastPage={lastPage}
            total={queue.total}
            noun="links waiting"
            labels={["Earlier", "Later"]}
            newer={page > 1 ? `/annotation?page=${page - 1}` : null}
            older={page < lastPage ? `/annotation?page=${page + 1}` : null}
          />
        )}

        {tab === "agreement" && stats && (
          <>
            <Panel
              id="matrix"
              title="How the first two annotators labelled the same links"
              description={`Rows: first judgement; columns: second. ${stats.percent === null ? "" : `They gave the same label ${(stats.percent * 100).toFixed(0)}% of the time.`} Disagreements on the diagonal are about which attributes are wrong.`}
            >
              {stats.items_with_two === 0 ? (
                <p className="text-sm text-muted">No link has two judgements yet.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="text-sm">
                    <caption className="sr-only">Confusion table of relation labels</caption>
                    <thead>
                      <tr>
                        <th scope="col" className="p-2 text-left text-muted">
                          First \ Second
                        </th>
                        {labels.map((l) => (
                          <th key={l} scope="col" className="p-2 text-right font-semibold">
                            {relationLabel(l)}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {labels.map((row) => (
                        <tr key={row} className="border-t border-line">
                          <th scope="row" className="p-2 text-left font-semibold">
                            {relationLabel(row)}
                          </th>
                          {labels.map((col) => {
                            const n = stats.matrix[row]?.[col] ?? 0;
                            return (
                              <td
                                key={col}
                                className={`p-2 text-right tabular-nums ${
                                  n === 0
                                    ? "text-muted/50"
                                    : row === col
                                      ? "bg-brand-soft font-semibold text-brand"
                                      : "bg-critical-soft font-semibold text-critical"
                                }`}
                              >
                                {n}
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Panel>

            <Panel
              id="decide"
              title="Disagreements to decide"
              description="Discuss each with the annotators, then record the final label. If the disagreement came from an unclear rule, update the annotation guideline."
            >
              {disagreements.length === 0 ? (
                <p className="text-sm text-muted">Nothing to decide.</p>
              ) : (
                <ul className="flex flex-col divide-y divide-line" aria-label="Disagreements">
                  {disagreements.map((d) => (
                    <li key={d.evidence_id} className="flex flex-col gap-3 py-4 first:pt-0">
                      <div className="grid gap-4 lg:grid-cols-2">
                        <EventBlock event={d.event} />
                        <ItemBlock report={d.field_report} signal={d.signal} />
                      </div>
                      <ul className="flex flex-col gap-1.5 text-sm" aria-label="Judgements">
                        {d.judgements.map((j) => (
                          <li key={j.id} className="flex flex-wrap items-center gap-2">
                            <span className="font-semibold">{j.annotator.full_name}:</span>
                            <Pill tone={j.relation === "unrelated" ? "grey" : "blue"}>
                              {relationLabel(j.relation)}
                            </Pill>
                            {j.conflicts.length > 0 && (
                              <span className="text-muted">
                                wrong: {j.conflicts.map(claimLabel).join(", ")}
                              </span>
                            )}
                            <span className="text-muted">
                              {CONFIDENCE.find(
                                (c) => c.value === j.confidence,
                              )?.label.toLowerCase()}
                              {j.stale ? ", out of date" : ""}
                            </span>
                            {j.note && <span className="text-muted">“{j.note}”</span>}
                          </li>
                        ))}
                      </ul>
                      <DecideForm
                        evidenceId={d.evidence_id}
                        options={[...new Set(d.judgements.map((j) => j.relation))]}
                      />
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          </>
        )}
      </PageBody>
    </>
  );
}
