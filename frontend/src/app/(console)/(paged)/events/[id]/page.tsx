import { History as HistoryIcon, LayoutGrid, Paperclip } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";

import { AssessmentText, EvidenceSummary, PriorityBadge } from "@/components/event-badges";
import { EvidenceControls, LinkButtons } from "@/components/evidence-controls";
import { PageBand, PageBody, Panel, Tabs } from "@/components/page-header";
import { SignalSummary } from "@/components/signal-bits";
import { api, ApiError } from "@/lib/api";
import { verifySession } from "@/lib/dal";
import { eventTypeIcon } from "@/lib/event-icons";
import { eventTypeLabel } from "@/lib/event-types";
import {
  assessmentLabel,
  familyLabel,
  priorityLabel,
  RELATION_STYLE,
  relationLabel,
  statusLabel,
} from "@/lib/events";
import { flagLabel, formatCoords, formatDhaka, isUuid } from "@/lib/format";
import {
  REPORT_REVIEWERS,
  type Assessment,
  type CandidateReport,
  type CandidateSignal,
  type CarcuxEvent,
  type EventStatus,
  type Evidence,
  type EvidenceRelation,
  type HistoryEntry,
  type Priority,
} from "@/lib/types";

import { GroundTruthPanel } from "./ground-truth-panel";
import { ManagePanel } from "./manage-panel";

export const metadata = { title: "Event" };

const FIELD_NAMES: Record<string, string> = {
  title: "title",
  summary: "summary",
  place_name: "place",
  event_type: "type",
  latitude: "latitude",
  longitude: "longitude",
  started_at: "start",
  ended_at: "end",
  status: "status",
  priority: "priority",
  assessment: "assessment",
  occurred: "whether it happened",
  ground_truth_sources: "ground truth sources",
  ground_truth_note: "ground truth note",
};

function showValue(field: string, value: unknown): string {
  if (value === null || value === undefined || value === "") return "nothing";
  if (Array.isArray(value)) return `${value.length} ${value.length === 1 ? "source" : "sources"}`;
  if (typeof value === "boolean") return value ? "yes" : "no";
  const v = String(value);
  if (field === "status") return statusLabel(v as EventStatus);
  if (field === "priority") return priorityLabel(v as Priority);
  if (field === "assessment") return assessmentLabel(v as Assessment);
  if (field === "event_type") return eventTypeLabel(v);
  if (field === "started_at" || field === "ended_at") return formatDhaka(v);
  if (field === "relation") return relationLabel(v as EvidenceRelation).toLowerCase();
  return v.length > 60 ? `“${v.slice(0, 57)}…”` : `“${v}”`;
}

/** One audit entry, in words. */
function describe(entry: HistoryEntry): React.ReactNode {
  const d = entry.details as Record<string, unknown>;
  const reportLink = d.signal_id ? (
    <Link href={`/signals/${String(d.signal_id)}`} className="text-brand hover:underline">
      a signal
    </Link>
  ) : d.field_report_id ? (
    <Link
      href={`/field-reports/${String(d.field_report_id)}`}
      className="text-brand hover:underline"
    >
      a report
    </Link>
  ) : (
    "a report"
  );
  switch (entry.action) {
    case "event.created": {
      const n = Number(d.reports ?? 0);
      const k = Number(d.signals ?? 0);
      const parts = [
        n ? `${n} ${n === 1 ? "report" : "reports"}` : "",
        k ? `${k} ${k === 1 ? "signal" : "signals"}` : "",
      ].filter(Boolean);
      return `created the event${parts.length ? ` from ${parts.join(" and ")}` : ""}`;
    }
    case "event.updated": {
      const changes = (d.changes ?? {}) as Record<string, [unknown, unknown]>;
      return `changed ${Object.entries(changes)
        .map(
          ([f, [from, to]]) =>
            `${FIELD_NAMES[f] ?? f} from ${showValue(f, from)} to ${showValue(f, to)}`,
        )
        .join("; ")}`;
    }
    case "event.evidence_linked":
      return (
        <>
          linked {reportLink} as {showValue("relation", d.relation)}
        </>
      );
    case "event.evidence_updated": {
      const rel = ((d.changes ?? {}) as Record<string, [unknown, unknown]>).relation;
      return rel ? (
        <>
          changed {reportLink} from {showValue("relation", rel[0])} to{" "}
          {showValue("relation", rel[1])}
        </>
      ) : (
        <>
          changed the{" "}
          {Object.keys((d.changes ?? {}) as object)
            .map(
              (k) =>
                ({ conflicts: "conflicts", stale: "out-of-date flag", confidence: "confidence" })[
                  k
                ] ?? k,
            )
            .join(" and ")}{" "}
          on {reportLink}
        </>
      );
    }
    case "event.evidence_unlinked":
      return (
        <>
          unlinked {reportLink} ({showValue("relation", d.relation)})
        </>
      );
    default:
      return entry.action;
  }
}

export default async function EventPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ created?: string; tab?: string }>;
}) {
  const user = await verifySession();
  const [{ id }, { created, tab: tabParam }] = await Promise.all([params, searchParams]);
  if (!isUuid(id)) notFound();

  let event: CarcuxEvent;
  try {
    event = await api<CarcuxEvent>(`/events/${id}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

  const reviewer = REPORT_REVIEWERS.includes(user.role);
  const tab =
    reviewer && (tabParam === "evidence" || tabParam === "history") ? tabParam : "overview";
  const open = event.status !== "dismissed";
  const [evidence, candidates, candidateSignals, history] = reviewer
    ? await Promise.all([
        api<Evidence[]>(`/events/${id}/evidence`),
        open
          ? api<CandidateReport[]>(`/events/${id}/candidate-reports`)
          : Promise.resolve([] as CandidateReport[]),
        open
          ? api<CandidateSignal[]>(`/events/${id}/candidate-signals`)
          : Promise.resolve([] as CandidateSignal[]),
        api<HistoryEntry[]>(`/events/${id}/history`),
      ])
    : [[] as Evidence[], [] as CandidateReport[], [] as CandidateSignal[], [] as HistoryEntry[]];

  const mapUrl = `https://www.openstreetmap.org/?mlat=${event.latitude}&mlon=${event.longitude}#map=16/${event.latitude}/${event.longitude}`;
  const base = `/events/${event.id}`;

  const details = (
    <Panel id="details" title="Details">
      <dl className="grid grid-cols-[6.5rem_1fr] gap-x-3 gap-y-2.5 text-sm">
        <dt className="text-muted">Type</dt>
        <dd>
          {eventTypeLabel(event.event_type)}, {familyLabel(event.family).toLowerCase()}
        </dd>
        <dt className="text-muted">Place</dt>
        <dd>{event.place_name ?? "Not named"}</dd>
        <dt className="text-muted">Location</dt>
        <dd>
          {formatCoords(event.latitude, event.longitude)}
          <a
            href={mapUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-2 font-semibold text-brand hover:underline"
          >
            Open map
          </a>
        </dd>
        <dt className="text-muted">Started</dt>
        <dd>{formatDhaka(event.started_at)}</dd>
        <dt className="text-muted">Ended</dt>
        <dd>{event.ended_at ? formatDhaka(event.ended_at) : "Ongoing"}</dd>
        <dt className="text-muted">Evidence</dt>
        <dd>
          <EvidenceSummary counts={event.evidence_counts} />
        </dd>
        <dt className="text-muted">Created by</dt>
        <dd>
          {event.created_by.full_name}, {formatDhaka(event.created_at)}
        </dd>
      </dl>
    </Panel>
  );

  return (
    <>
      <PageBand
        scene="padma"
        icon={eventTypeIcon(event.event_type)}
        back={{ href: "/events", label: "All events" }}
        kicker={eventTypeLabel(event.event_type)}
        title={event.title}
      >
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded bg-white px-0.5 py-0.5">
            <PriorityBadge priority={event.priority} />
          </span>
          <span className="rounded bg-white px-2 py-0.5 text-sm">
            <AssessmentText assessment={event.assessment} />
          </span>
          <span className="rounded bg-white/15 px-2 py-0.5 text-sm">
            {statusLabel(event.status)}
          </span>
        </div>
      </PageBand>

      <PageBody>
        {created && (
          <p role="status" className="rounded-md border border-ok/40 bg-brand-soft px-3 py-2">
            Event created. Link more reports under Evidence as they come in.
          </p>
        )}

        {reviewer && (
          <Tabs
            active={tab}
            items={[
              {
                key: "overview",
                label: "Overview",
                href: base,
                icon: LayoutGrid,
              },
              {
                key: "evidence",
                label: "Evidence",
                icon: Paperclip,
                href: `${base}?tab=evidence`,
                count: evidence.length,
              },
              {
                key: "history",
                label: "History",
                href: `${base}?tab=history`,
                count: history.length,
                icon: HistoryIcon,
              },
            ]}
          />
        )}

        {tab === "overview" && (
          <div className="grid gap-6 lg:grid-cols-[1fr_22rem] lg:items-start">
            <div className="flex min-w-0 flex-col gap-6">
              <Panel id="summary" title="Summary">
                {event.summary ? (
                  <p className="text-[17px] leading-relaxed whitespace-pre-wrap">{event.summary}</p>
                ) : (
                  <p className="text-muted">
                    No summary yet.
                    {reviewer && " Add one with Edit title, place and summary."}
                  </p>
                )}
              </Panel>
              {details}
            </div>
            {reviewer && (
              <div className="flex flex-col gap-6">
                <Panel id="manage" title="Analyst decision">
                  <ManagePanel event={event} />
                </Panel>
                <Panel
                  id="ground-truth"
                  title="Ground truth"
                  description="What really happened, from sources published afterwards. Needed before the event can go into the CARCUX-BD dataset."
                >
                  <GroundTruthPanel event={event} />
                </Panel>
              </div>
            )}
          </div>
        )}

        {tab === "evidence" && (
          <div className="flex flex-col gap-6">
            <Panel
              id="evidence"
              title="Linked evidence"
              description="Field reports and public signals placed against this event, and how each bears on it."
            >
              {evidence.length === 0 ? (
                <p className="text-sm text-muted">Nothing linked yet.</p>
              ) : (
                <ul className="flex flex-col gap-4">
                  {evidence.map((item) => {
                    const r = item.field_report;
                    if (!r) {
                      return item.signal ? (
                        <li
                          key={item.id}
                          className={`rounded-md border border-line border-l-4 bg-panel p-3 ${RELATION_STYLE[item.relation]}`}
                        >
                          <p className="mb-1 text-xs font-bold tracking-wide text-[#2f7fb0] uppercase">
                            Public signal
                          </p>
                          <div className="mb-2">
                            <SignalSummary signal={item.signal} />
                          </div>
                          <EvidenceControls
                            eventId={event.id}
                            evidenceId={item.id}
                            relation={item.relation}
                            conflicts={item.conflicts}
                            stale={item.stale}
                            confidence={item.confidence}
                            noun="signal"
                          />
                          <p className="mt-1 text-xs text-muted">
                            Linked by {item.linked_by.full_name}, {formatDhaka(item.linked_at)}
                          </p>
                        </li>
                      ) : null;
                    }
                    return (
                      <li
                        key={item.id}
                        className={`rounded-md border border-line border-l-4 bg-panel p-3 ${RELATION_STYLE[item.relation]}`}
                      >
                        <p className="mb-1 text-xs font-bold tracking-wide text-brand uppercase">
                          Field report
                        </p>
                        <p className="flex flex-wrap gap-x-3 text-sm text-muted">
                          <span>{formatDhaka(r.observed_at)}</span>
                          <span>{r.reporter.full_name}</span>
                          {r.place_name && <span>{r.place_name}</span>}
                          {r.media.length > 0 && (
                            <span>
                              {r.media.length} {r.media.length === 1 ? "photo" : "photos"}
                            </span>
                          )}
                        </p>
                        <p className="mb-2">
                          <Link
                            href={`/field-reports/${r.id}`}
                            className="hover:text-brand hover:underline"
                          >
                            {r.text}
                          </Link>
                        </p>
                        {r.integrity_flags.length > 0 && (
                          <p className="mb-2 flex flex-wrap gap-2 text-xs">
                            {r.integrity_flags.map((f, i) => (
                              <span
                                key={i}
                                className="rounded bg-critical-soft px-2 py-0.5 text-critical ring-1 ring-critical/30"
                              >
                                {flagLabel(f.code)}
                              </span>
                            ))}
                          </p>
                        )}
                        <EvidenceControls
                          eventId={event.id}
                          evidenceId={item.id}
                          reportId={r.id}
                          relation={item.relation}
                          conflicts={item.conflicts}
                          stale={item.stale}
                          confidence={item.confidence}
                        />
                        <p className="mt-1 text-xs text-muted">
                          Linked by {item.linked_by.full_name}, {formatDhaka(item.linked_at)}
                        </p>
                      </li>
                    );
                  })}
                </ul>
              )}
            </Panel>

            {open && (
              <Panel
                id="candidates"
                title="Possibly related reports"
                description="Unlinked reports within 5 km and 48 hours, same type first. Chosen by place and time only: read each one before linking it."
              >
                {candidates.length === 0 ? (
                  <p className="text-sm text-muted">None right now.</p>
                ) : (
                  <ul className="flex flex-col divide-y divide-line">
                    {candidates.map((c) => (
                      <li
                        key={c.report.id}
                        className="flex flex-col gap-3 py-3 first:pt-0 last:pb-0"
                      >
                        <div>
                          <p className="flex flex-wrap gap-x-3 text-sm text-muted">
                            <span>
                              {c.distance_km < 1
                                ? `${Math.round(c.distance_km * 1000)} m away`
                                : `${c.distance_km.toFixed(1)} km away`}
                            </span>
                            <span>
                              {c.hours_apart === 0
                                ? "during the event"
                                : `${c.hours_apart} h outside the event's time`}
                            </span>
                            {c.same_type ? (
                              <span className="font-semibold text-brand">same type</span>
                            ) : (
                              <span>{eventTypeLabel(c.report.event_type)}</span>
                            )}
                            <span>{c.report.reporter.full_name}</span>
                          </p>
                          <Link
                            href={`/field-reports/${c.report.id}`}
                            className="hover:text-brand hover:underline"
                          >
                            {c.report.text}
                          </Link>
                        </div>
                        <LinkButtons
                          eventId={event.id}
                          reportId={c.report.id}
                          label="Link this report as"
                        />
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>
            )}

            {open && (
              <Panel
                id="candidate-signals"
                title="Possibly related signals"
                description="Alerts, bulletins and news whose area and time overlap this event. A district-level news item covers its whole district: check the place before linking."
              >
                {candidateSignals.length === 0 ? (
                  <p className="text-sm text-muted">None right now.</p>
                ) : (
                  <ul className="flex flex-col divide-y divide-line">
                    {candidateSignals.map((c) => (
                      <li
                        key={c.signal.id}
                        className="flex flex-col gap-3 py-3 first:pt-0 last:pb-0"
                      >
                        <div className="flex flex-col gap-1">
                          <p className="flex flex-wrap gap-x-3 text-sm text-muted">
                            <span>
                              {c.distance_km < 1
                                ? `${Math.round(c.distance_km * 1000)} m away`
                                : `${c.distance_km.toFixed(1)} km away`}
                            </span>
                            <span>
                              {c.hours_apart === 0
                                ? "during the event"
                                : `${c.hours_apart} h outside the event's time`}
                            </span>
                            {c.same_type && (
                              <span className="font-semibold text-brand">same type</span>
                            )}
                          </p>
                          <SignalSummary signal={c.signal} />
                        </div>
                        <LinkButtons
                          eventId={event.id}
                          signalId={c.signal.id}
                          label="Link this signal as"
                        />
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>
            )}
          </div>
        )}

        {tab === "history" && (
          <Panel id="history" title="History">
            <ol className="relative flex flex-col gap-4 border-l-2 border-line pl-5 text-sm">
              {history.map((h, i) => (
                <li key={i} className="relative">
                  <span
                    aria-hidden="true"
                    className={`absolute top-1.5 -left-[27px] h-3 w-3 rounded-full border-2 border-panel ${
                      h.action === "event.created" ? "bg-red" : "bg-brand"
                    }`}
                  />
                  <p className="text-muted">{formatDhaka(h.occurred_at)}</p>
                  <p>
                    <span className="font-semibold text-ink">{h.actor?.full_name ?? "System"}</span>{" "}
                    <span className="text-muted">{describe(h)}</span>
                  </p>
                </li>
              ))}
            </ol>
          </Panel>
        )}
      </PageBody>
    </>
  );
}
