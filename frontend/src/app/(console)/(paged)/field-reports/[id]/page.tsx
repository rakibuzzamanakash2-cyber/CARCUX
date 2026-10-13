import { LayoutGrid, Radar, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";

import { AssessmentText, PriorityBadge, StatusText } from "@/components/event-badges";
import { LinkButtons } from "@/components/evidence-controls";
import { ReviewControls } from "@/components/review-controls";
import { buttonSecondary, PageBand, PageBody, Panel, Tabs } from "@/components/page-header";
import { api, ApiError } from "@/lib/api";
import { requireRole } from "@/lib/dal";
import { eventTypeIcon } from "@/lib/event-icons";
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
        className="font-semibold text-brand hover:underline"
      >
        {part.slice(0, 8)}
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
  searchParams: Promise<{ submitted?: string; tab?: string }>;
}) {
  const user = await requireRole(...REPORT_READERS);
  const [{ id }, { submitted, tab: tabParam }] = await Promise.all([params, searchParams]);
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
  const tab =
    reviewer && (tabParam === "integrity" || tabParam === "events") ? tabParam : "overview";
  const [links, candidates] = reviewer
    ? await Promise.all([
        api<ReportLink[]>(`/field-reports/${id}/events`),
        api<CandidateEvent[]>(`/field-reports/${id}/candidate-events`),
      ])
    : [[] as ReportLink[], [] as CandidateEvent[]];
  const mapUrl = `https://www.openstreetmap.org/?mlat=${report.latitude}&mlon=${report.longitude}#map=17/${report.latitude}/${report.longitude}`;
  const base = `/field-reports/${report.id}`;
  const flags = report.integrity_flags;

  return (
    <>
      <PageBand
        scene="padma"
        icon={eventTypeIcon(report.event_type)}
        back={{ href: "/field-reports", label: "All field reports" }}
        kicker={
          <span className="flex flex-wrap gap-x-3">
            <span>{eventTypeLabel(report.event_type)}</span>
            {report.place_name && <span>{report.place_name}</span>}
          </span>
        }
        title="Field report"
        description={`${report.reporter.full_name}, seen ${formatDhaka(report.observed_at)}`}
      >
        {reviewer && flags.length > 0 && (
          <span className="inline-flex items-center gap-1.5 rounded bg-red px-2 py-0.5 text-sm font-semibold">
            {flags.length} {flags.length === 1 ? "flag" : "flags"} to look at
          </span>
        )}
      </PageBand>

      <PageBody>
        {submitted && (
          <div
            role="status"
            className="flex flex-col gap-3 rounded-md border border-ok/40 bg-brand-soft px-3 py-2 sm:flex-row sm:items-center sm:justify-between"
          >
            <p>
              {submitted === "new"
                ? "Report sent. Analysts can see it now."
                : "This report had already arrived, so nothing was sent twice."}
            </p>
            {canSubmit && (
              <Link
                href="/field-reports/new"
                className="text-sm font-semibold text-brand hover:underline"
              >
                Send another report
              </Link>
            )}
          </div>
        )}

        {reviewer && (
          <Tabs
            active={tab}
            items={[
              { key: "overview", label: "Overview", href: base, icon: LayoutGrid },
              {
                key: "integrity",
                label: "Integrity",
                icon: ShieldCheck,
                href: `${base}?tab=integrity`,
                count: flags.length,
              },
              {
                key: "events",
                label: "Events",
                href: `${base}?tab=events`,
                count: links.length,
                icon: Radar,
              },
            ]}
          />
        )}

        {tab === "overview" && (
          <div className="grid gap-6 lg:grid-cols-[1fr_22rem] lg:items-start">
            <div className="flex min-w-0 flex-col gap-6">
              <Panel id="report" title="What they saw">
                <p className="text-[17px] leading-relaxed whitespace-pre-wrap">{report.text}</p>
              </Panel>
              <Panel id="photos" title="Photos">
                {report.media.length === 0 ? (
                  <p className="text-sm text-muted">No photos with this report.</p>
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
                              className="h-auto w-full rounded-md border border-line bg-panel-2"
                            />
                          </a>
                          <p className="text-xs text-muted">
                            {m.width} × {m.height} px, {formatBytes(m.size_bytes)}
                          </p>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </Panel>
            </div>
            <div className="flex flex-col gap-6">
              <Panel id="details" title="Details">
                <dl className="grid grid-cols-[6.5rem_1fr] gap-x-3 gap-y-2.5 text-sm">
                  <dt className="text-muted">Seen at</dt>
                  <dd>{formatDhaka(report.observed_at)}</dd>
                  <dt className="text-muted">Received</dt>
                  <dd>{formatDhaka(report.received_at)}</dd>
                  <dt className="text-muted">Reported by</dt>
                  <dd>{report.reporter.full_name}</dd>
                  <dt className="text-muted">Location</dt>
                  <dd>
                    {formatCoords(report.latitude, report.longitude)}
                    {report.location_accuracy_m !== null && (
                      <span className="text-muted">
                        {" "}
                        (±{Math.round(report.location_accuracy_m)} m)
                      </span>
                    )}
                    <a
                      href={mapUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="block font-semibold text-brand hover:underline"
                    >
                      Open map
                    </a>
                  </dd>
                  <dt className="text-muted">Status</dt>
                  <dd>
                    {
                      {
                        submitted: "New, waiting for review",
                        reviewed: "Reviewed",
                        dismissed: "Dismissed",
                      }[report.status]
                    }
                    {report.reviewed_by && report.reviewed_at && (
                      <span className="block text-muted">
                        by {report.reviewed_by.full_name}, {formatDhaka(report.reviewed_at)}
                      </span>
                    )}
                    {report.review_note && (
                      <span className="mt-1 block rounded-md bg-panel-2 px-2 py-1">
                        {report.review_note}
                      </span>
                    )}
                  </dd>
                </dl>
              </Panel>
              {reviewer && (
                <Panel
                  id="triage"
                  title="Triage"
                  description="Linking it to an event also marks it reviewed."
                >
                  <ReviewControls reportId={report.id} status={report.status} compact />
                </Panel>
              )}
            </div>
          </div>
        )}

        {tab === "integrity" && (
          <div className="grid gap-6 lg:grid-cols-[1fr_22rem] lg:items-start">
            {/* Field workers never reach this tab: flags are prompts for reviewers, and
                showing them to submitters teaches how to avoid them. */}
            <Panel id="flags" title="Look closer" tone={flags.length ? "critical" : undefined}>
              {flags.length === 0 ? (
                <p className="text-sm text-muted">No integrity checks raised anything.</p>
              ) : (
                <ul className="flex flex-col gap-4">
                  {flags.map((f, i) => (
                    <li key={`${f.code}-${i}`} className="border-l-4 border-critical pl-3">
                      <p className="font-semibold text-critical">{flagLabel(f.code)}</p>
                      <p className="text-sm">{linkReports(f.detail)}</p>
                      {FLAG_INFO[f.code] && (
                        <p className="mt-1 text-sm text-muted">{FLAG_INFO[f.code].meaning}</p>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
            <Panel
              id="integrity"
              title="Fingerprint"
              description="Taken when the report arrived, over its text, location, time and every photo. Any later edit breaks the match."
            >
              <p className="mb-4 text-xs break-all text-muted">{report.content_hash}</p>
              <VerifyPanel reportId={report.id} />
            </Panel>
          </div>
        )}

        {tab === "events" && (
          <Panel id="events" title="Events">
            {links.length > 0 && (
              <ul className="mb-5 flex flex-col gap-3">
                {links.map((l) => (
                  <li
                    key={l.evidence_id}
                    className={`rounded-md border border-line border-l-4 p-3 ${RELATION_STYLE[l.relation]}`}
                  >
                    <p className="text-sm text-muted">
                      This report {relationLabel(l.relation).toLowerCase()}
                    </p>
                    <Link
                      href={`/events/${l.event.id}`}
                      className="font-semibold hover:text-brand hover:underline"
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
                <p className="mb-3 text-sm text-muted">
                  Open events within 5 km and 48 hours of this report, same type first. Read the
                  event before linking.
                </p>
                <ul className="mb-5 flex flex-col divide-y divide-line">
                  {candidates.map((c) => (
                    <li key={c.event.id} className="flex flex-col gap-3 py-3">
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
                              : `${c.hours_apart} h outside it`}
                          </span>
                          {c.same_type ? (
                            <span className="font-semibold text-brand">same type</span>
                          ) : (
                            <span>{eventTypeLabel(c.event.event_type)}</span>
                          )}
                        </p>
                        <Link
                          href={`/events/${c.event.id}`}
                          className="font-semibold hover:text-brand hover:underline"
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
                <p className="mb-4 text-sm text-muted">
                  Not linked to any event, and no open event is nearby.
                </p>
              )
            )}
            <Link href={`/events/new?from_report=${report.id}`} className={buttonSecondary}>
              Create an event from this report
            </Link>
          </Panel>
        )}
      </PageBody>
    </>
  );
}
