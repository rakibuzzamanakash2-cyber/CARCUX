import Link from "next/link";
import { notFound } from "next/navigation";

import { AssessmentText, PriorityBadge, StatusText } from "@/components/event-badges";
import { LinkButtons } from "@/components/evidence-controls";
import { api, ApiError } from "@/lib/api";
import { requireRole } from "@/lib/dal";
import { eventTypeLabel } from "@/lib/event-types";
import { RELATION_STYLE, relationLabel } from "@/lib/events";
import { FLAG_INFO, flagLabel, formatBytes, formatCoords, formatDhaka, isUuid } from "@/lib/format";
import {
  REPORT_READERS,
  REPORT_REVIEWERS,
  REPORT_SUBMITTERS,
  type CandidateEvent,
  type FieldReport,
  type ReportLink,
} from "@/lib/types";

import { VerifyPanel } from "./verify-panel";

export const metadata = { title: "Field report" };

const UUID_IN_TEXT = /([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/gi;

/** Turn report ids inside a flag's detail into links to those reports. */
function linkReports(text: string) {
  return text.split(UUID_IN_TEXT).map((part, i) =>
    isUuid(part) ? (
      <Link
        key={i}
        href={`/field-reports/${part}`}
        className="underline underline-offset-2 hover:text-white"
      >
        report {part.slice(0, 8)}
      </Link>
    ) : (
      part
    ),
  );
}

export default async function FieldReportPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ submitted?: string }>;
}) {
  const user = await requireRole(...REPORT_READERS);
  const [{ id }, { submitted }] = await Promise.all([params, searchParams]);
  if (!isUuid(id)) notFound();

  let report: FieldReport;
  try {
    report = await api<FieldReport>(`/field-reports/${id}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

  const reviewer = REPORT_REVIEWERS.includes(user.role);
  const canSubmit = REPORT_SUBMITTERS.includes(user.role);
  const [links, candidates] = reviewer
    ? await Promise.all([
        api<ReportLink[]>(`/field-reports/${id}/events`),
        api<CandidateEvent[]>(`/field-reports/${id}/candidate-events`),
      ])
    : [[] as ReportLink[], [] as CandidateEvent[]];
  const mapUrl = `https://www.openstreetmap.org/?mlat=${report.latitude}&mlon=${report.longitude}#map=17/${report.latitude}/${report.longitude}`;

  return (
    <div className="flex flex-col gap-10">
      <Link href="/field-reports" className="w-fit text-sm text-steel hover:text-bone">
        ← All field reports
      </Link>

      {submitted && (
        <div
          role="status"
          className="flex flex-col gap-3 border-l-2 border-ok pl-3 sm:flex-row sm:items-center sm:justify-between"
        >
          <p>
            {submitted === "new"
              ? "Report sent. Analysts can see it now."
              : "This report had already arrived, so nothing was sent twice."}
          </p>
          {canSubmit && (
            <Link
              href="/field-reports/new"
              className="text-sm text-steel underline underline-offset-2 hover:text-bone"
            >
              Send another report
            </Link>
          )}
        </div>
      )}

      <section>
        <p className="mb-2 text-sm text-steel">
          {eventTypeLabel(report.event_type)}
          {report.place_name && <span> · {report.place_name}</span>}
        </p>
        <h1 className="display mb-4 text-3xl sm:text-4xl">Field report</h1>
        <p className="max-w-3xl whitespace-pre-wrap text-lg leading-relaxed">{report.text}</p>
      </section>

      {/* Field workers do not see integrity flags: they are prompts for reviewers,
          and showing them to submitters teaches how to avoid them. */}
      {reviewer && report.integrity_flags.length > 0 && (
        <section aria-labelledby="flags" className="border-t border-line pt-6">
          <h2 id="flags" className="display mb-4 text-2xl">
            Look closer
          </h2>
          <ul className="flex max-w-3xl flex-col gap-4">
            {report.integrity_flags.map((f, i) => (
              <li key={`${f.code}-${i}`} className="border-l-2 border-signal pl-3">
                <p className="font-semibold">{flagLabel(f.code)}</p>
                <p className="text-sm">{linkReports(f.detail)}</p>
                {FLAG_INFO[f.code] && (
                  <p className="mt-1 text-sm text-steel">{FLAG_INFO[f.code].meaning}</p>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {reviewer && (
        <section aria-labelledby="events" className="border-t border-line pt-6">
          <h2 id="events" className="display mb-4 text-2xl">
            Events
          </h2>
          {links.length > 0 && (
            <ul className="mb-6 flex max-w-3xl flex-col gap-3">
              {links.map((l) => (
                <li key={l.evidence_id} className={`border-l-2 pl-3 ${RELATION_STYLE[l.relation]}`}>
                  <p className="text-sm text-steel">
                    This report {relationLabel(l.relation).toLowerCase()}
                  </p>
                  <Link
                    href={`/events/${l.event.id}`}
                    className="hover:underline hover:underline-offset-2"
                  >
                    {l.event.title}
                  </Link>
                  <p className="mt-1 flex flex-wrap items-center gap-3 text-sm">
                    <PriorityBadge priority={l.event.priority} />
                    <AssessmentText assessment={l.event.assessment} />
                    <StatusText status={l.event.status} />
                  </p>
                </li>
              ))}
            </ul>
          )}
          {candidates.length > 0 ? (
            <>
              <h3 className="mb-1 font-semibold">Possibly the same situation</h3>
              <p className="mb-4 max-w-3xl text-sm text-steel">
                Open events within 5 km and 48 hours of this report, same type first. Read the event
                before linking.
              </p>
              <ul className="mb-6 flex max-w-4xl flex-col divide-y divide-line border-y border-line">
                {candidates.map((c) => (
                  <li key={c.event.id} className="flex flex-col gap-3 py-4">
                    <div>
                      <p className="text-sm text-steel">
                        {c.distance_km < 1
                          ? `${Math.round(c.distance_km * 1000)} m away`
                          : `${c.distance_km.toFixed(1)} km away`}
                        {" · "}
                        {c.hours_apart === 0 ? "during the event" : `${c.hours_apart} h outside it`}
                        {" · "}
                        {c.same_type ? (
                          <span className="text-bone">same type</span>
                        ) : (
                          eventTypeLabel(c.event.event_type)
                        )}
                      </p>
                      <Link
                        href={`/events/${c.event.id}`}
                        className="hover:underline hover:underline-offset-2"
                      >
                        {c.event.title}
                      </Link>
                    </div>
                    <LinkButtons
                      eventId={c.event.id}
                      reportId={report.id}
                      label="Link to this event as"
                    />
                  </li>
                ))}
              </ul>
            </>
          ) : (
            links.length === 0 && (
              <p className="mb-4 text-sm text-steel">
                Not linked to any event, and no open event is nearby.
              </p>
            )
          )}
          <Link
            href={`/events/new?from_report=${report.id}`}
            className="inline-flex h-11 items-center rounded-sm border border-steel px-4 text-bone transition-colors hover:bg-panel-2"
          >
            Create an event from this report
          </Link>
        </section>
      )}

      <section aria-labelledby="details" className="border-t border-line pt-6">
        <h2 id="details" className="display mb-4 text-2xl">
          Details
        </h2>
        <dl className="grid max-w-3xl grid-cols-[9rem_1fr] gap-x-4 gap-y-2 text-sm sm:grid-cols-[11rem_1fr]">
          <dt className="text-steel">Seen at</dt>
          <dd>{formatDhaka(report.observed_at)}</dd>
          <dt className="text-steel">Received</dt>
          <dd>{formatDhaka(report.received_at)}</dd>
          <dt className="text-steel">Reported by</dt>
          <dd>{report.reporter.full_name}</dd>
          <dt className="text-steel">Location</dt>
          <dd>
            {formatCoords(report.latitude, report.longitude)}
            {report.location_accuracy_m !== null && (
              <span className="text-steel"> (±{Math.round(report.location_accuracy_m)} m)</span>
            )}
            <a
              href={mapUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="ml-3 text-steel underline underline-offset-2 hover:text-bone"
            >
              Open map
            </a>
          </dd>
          <dt className="text-steel">Status</dt>
          <dd className="capitalize">{report.status}</dd>
        </dl>
      </section>

      <section aria-labelledby="photos" className="border-t border-line pt-6">
        <h2 id="photos" className="display mb-4 text-2xl">
          Photos
        </h2>
        {report.media.length === 0 ? (
          <p className="text-sm text-steel">No photos with this report.</p>
        ) : (
          <ul className="grid gap-4 sm:grid-cols-2">
            {report.media.map((m) => {
              const src = `/field-reports/${report.id}/photos/${m.id}`;
              return (
                <li key={m.id} className="flex flex-col gap-2">
                  <a href={src} target="_blank" rel="noopener" title="Open full size">
                    {/* Authenticated, uncached photo: next/image would cache it. */}
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={src}
                      alt={`Photo ${m.position + 1} from this report`}
                      width={m.width}
                      height={m.height}
                      loading="lazy"
                      className="h-auto w-full rounded-sm border border-line bg-panel"
                    />
                  </a>
                  <p className="text-xs text-steel">
                    {m.width} × {m.height} · {formatBytes(m.size_bytes)}
                  </p>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section aria-labelledby="integrity" className="border-t border-line pt-6">
        <h2 id="integrity" className="display mb-2 text-2xl">
          Fingerprint
        </h2>
        <p className="mb-4 max-w-3xl text-sm text-steel">
          Taken when the report arrived, over its text, location, time and every photo. If anything
          is edited later, it no longer matches.
        </p>
        <p className="mb-5 font-mono text-xs break-all text-steel">{report.content_hash}</p>
        {reviewer && <VerifyPanel reportId={report.id} />}
      </section>
    </div>
  );
}
