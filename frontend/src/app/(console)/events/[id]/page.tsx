import Link from "next/link";
import { notFound } from "next/navigation";

import {
  AssessmentText,
  EvidenceSummary,
  PriorityBadge,
  StatusText,
} from "@/components/event-badges";
import { EvidenceControls, LinkButtons } from "@/components/evidence-controls";
import { api, ApiError } from "@/lib/api";
import { verifySession } from "@/lib/dal";
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
  type CarcuxEvent,
  type EventStatus,
  type Evidence,
  type EvidenceRelation,
  type HistoryEntry,
  type Priority,
} from "@/lib/types";

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
};

function showValue(field: string, value: unknown): string {
  if (value === null || value === undefined || value === "") return "nothing";
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
  const reportLink = d.field_report_id ? (
    <Link
      href={`/field-reports/${String(d.field_report_id)}`}
      className="underline underline-offset-2 hover:text-white"
    >
      a report
    </Link>
  ) : (
    "a report"
  );
  switch (entry.action) {
    case "event.created": {
      const n = Number(d.reports ?? 0);
      return `created the event${n ? ` from ${n} ${n === 1 ? "report" : "reports"}` : ""}`;
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
        <>changed the note on {reportLink}</>
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
  searchParams: Promise<{ created?: string }>;
}) {
  const user = await verifySession();
  const [{ id }, { created }] = await Promise.all([params, searchParams]);
  if (!isUuid(id)) notFound();

  let event: CarcuxEvent;
  try {
    event = await api<CarcuxEvent>(`/events/${id}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

  const reviewer = REPORT_REVIEWERS.includes(user.role);
  const [evidence, candidates, history] = reviewer
    ? await Promise.all([
        api<Evidence[]>(`/events/${id}/evidence`),
        event.status === "dismissed"
          ? Promise.resolve([] as CandidateReport[])
          : api<CandidateReport[]>(`/events/${id}/candidate-reports`),
        api<HistoryEntry[]>(`/events/${id}/history`),
      ])
    : [[] as Evidence[], [] as CandidateReport[], [] as HistoryEntry[]];

  const mapUrl = `https://www.openstreetmap.org/?mlat=${event.latitude}&mlon=${event.longitude}#map=16/${event.latitude}/${event.longitude}`;

  return (
    <div className="flex flex-col gap-10">
      <Link href="/events" className="w-fit text-sm text-steel hover:text-bone">
        ← All events
      </Link>

      {created && (
        <p role="status" className="border-l-2 border-ok pl-3">
          Event created. Link more reports below as they come in.
        </p>
      )}

      <section>
        <p className="mb-2 text-sm text-steel">
          {eventTypeLabel(event.event_type)} · {familyLabel(event.family)}
        </p>
        <h1 className="display mb-4 text-3xl sm:text-4xl">{event.title}</h1>
        <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
          <PriorityBadge priority={event.priority} />
          <AssessmentText assessment={event.assessment} />
          <StatusText status={event.status} />
        </div>
        {event.summary && (
          <p className="max-w-3xl text-lg leading-relaxed whitespace-pre-wrap">{event.summary}</p>
        )}
      </section>

      <section aria-labelledby="details" className="border-t border-line pt-6">
        <h2 id="details" className="display mb-4 text-2xl">
          Details
        </h2>
        <dl className="grid max-w-3xl grid-cols-[9rem_1fr] gap-x-4 gap-y-2 text-sm sm:grid-cols-[11rem_1fr]">
          <dt className="text-steel">Place</dt>
          <dd>{event.place_name ?? "Not named"}</dd>
          <dt className="text-steel">Location</dt>
          <dd>
            {formatCoords(event.latitude, event.longitude)}
            <a
              href={mapUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="ml-3 text-steel underline underline-offset-2 hover:text-bone"
            >
              Open map
            </a>
          </dd>
          <dt className="text-steel">Started</dt>
          <dd>{formatDhaka(event.started_at)}</dd>
          <dt className="text-steel">Ended</dt>
          <dd>{event.ended_at ? formatDhaka(event.ended_at) : "Ongoing"}</dd>
          <dt className="text-steel">Evidence</dt>
          <dd>
            <EvidenceSummary counts={event.evidence_counts} />
          </dd>
          <dt className="text-steel">Created by</dt>
          <dd>
            {event.created_by.full_name}, {formatDhaka(event.created_at)}
          </dd>
        </dl>
      </section>

      {reviewer && (
        <>
          <section aria-labelledby="manage" className="border-t border-line pt-6">
            <h2 id="manage" className="display mb-4 text-2xl">
              Analyst decision
            </h2>
            <ManagePanel event={event} />
          </section>

          <section aria-labelledby="evidence" className="border-t border-line pt-6">
            <h2 id="evidence" className="display mb-1 text-2xl">
              Evidence
            </h2>
            <p className="mb-5 text-sm text-steel">
              Reports placed against this event, and how each bears on it.
            </p>
            {evidence.length === 0 ? (
              <p className="text-sm text-steel">No reports linked yet.</p>
            ) : (
              <ul className="flex max-w-4xl flex-col gap-5">
                {evidence.map((item) => {
                  const r = item.field_report;
                  return (
                    <li
                      key={item.id}
                      className={`border-l-2 pl-4 ${RELATION_STYLE[item.relation]}`}
                    >
                      <p className="text-sm text-steel">
                        {formatDhaka(r.observed_at)} · {r.reporter.full_name}
                        {r.place_name && <span> · {r.place_name}</span>}
                        {r.media.length > 0 && (
                          <span>
                            {" "}
                            · {r.media.length} {r.media.length === 1 ? "photo" : "photos"}
                          </span>
                        )}
                      </p>
                      <p className="mb-1">
                        <Link
                          href={`/field-reports/${r.id}`}
                          className="hover:underline hover:underline-offset-2"
                        >
                          {r.text}
                        </Link>
                      </p>
                      {r.integrity_flags.length > 0 && (
                        <p className="mb-2 flex flex-wrap gap-2 text-xs">
                          {r.integrity_flags.map((f, i) => (
                            <span key={i} className="rounded-sm bg-signal-soft px-2 py-0.5">
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
                      />
                      <p className="mt-1 text-xs text-steel">
                        Linked by {item.linked_by.full_name}, {formatDhaka(item.linked_at)}
                      </p>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          {event.status !== "dismissed" && (
            <section aria-labelledby="candidates" className="border-t border-line pt-6">
              <h2 id="candidates" className="display mb-1 text-2xl">
                Possibly related reports
              </h2>
              <p className="mb-5 max-w-3xl text-sm text-steel">
                Unlinked reports within 5 km and 48 hours of this event, same type first. A
                suggestion from location and time only: read each one before linking it.
              </p>
              {candidates.length === 0 ? (
                <p className="text-sm text-steel">None right now.</p>
              ) : (
                <ul className="flex max-w-4xl flex-col divide-y divide-line border-y border-line">
                  {candidates.map((c) => (
                    <li key={c.report.id} className="flex flex-col gap-3 py-4">
                      <div>
                        <p className="text-sm text-steel">
                          {c.distance_km < 1
                            ? `${Math.round(c.distance_km * 1000)} m away`
                            : `${c.distance_km.toFixed(1)} km away`}
                          {" · "}
                          {c.hours_apart === 0
                            ? "during the event"
                            : `${c.hours_apart} h outside the event's time`}
                          {" · "}
                          {c.same_type ? (
                            <span className="text-bone">same type</span>
                          ) : (
                            eventTypeLabel(c.report.event_type)
                          )}
                          {" · "}
                          {c.report.reporter.full_name}
                        </p>
                        <Link
                          href={`/field-reports/${c.report.id}`}
                          className="hover:underline hover:underline-offset-2"
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
            </section>
          )}

          <section aria-labelledby="history" className="border-t border-line pt-6">
            <h2 id="history" className="display mb-4 text-2xl">
              History
            </h2>
            <ol className="flex max-w-3xl flex-col gap-2 text-sm">
              {history.map((h, i) => (
                <li key={i} className="grid gap-1 sm:grid-cols-[10rem_1fr] sm:gap-4">
                  <span className="text-steel">{formatDhaka(h.occurred_at)}</span>
                  <span>
                    <span className="text-bone">{h.actor?.full_name ?? "System"}</span>{" "}
                    <span className="text-steel">{describe(h)}</span>
                  </span>
                </li>
              ))}
            </ol>
          </section>
        </>
      )}
    </div>
  );
}
