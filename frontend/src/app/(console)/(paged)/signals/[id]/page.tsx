import { ExternalLink, Plus } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";

import { LinkButtons } from "@/components/evidence-controls";
import { buttonSecondary, PageBand, PageBody, Panel } from "@/components/page-header";
import { ReviewControls } from "@/components/review-controls";
import { SeverityPill, SignalStatusPill } from "@/components/signal-bits";
import { api, ApiError } from "@/lib/api";
import { verifySession } from "@/lib/dal";
import { eventTypeIcon } from "@/lib/event-icons";
import { eventTypeLabel } from "@/lib/event-types";
import { relationLabel } from "@/lib/events";
import { formatCoords, formatDhaka, isUuid } from "@/lib/format";
import { ADAPTER, LANGUAGE_LABEL, precisionText, SOURCE_TYPE_LABEL } from "@/lib/signals";
import { REPORT_REVIEWERS, type CandidateEvent, type ReportLink, type Signal } from "@/lib/types";

export const metadata = { title: "Signal" };

/** Why CARCUX kept and placed this item, from what the adapter recorded. */
function HowFound({ signal }: { signal: Signal }) {
  const x = signal.extraction;
  const lines: string[] = [];
  if (Array.isArray(x.matched) && x.matched.length)
    lines.push(
      `Matched ${x.matched.map((w) => `“${String(w)}”`).join(", ")}${x.matched_in_headline ? " in the headline" : " in the summary"}.`,
    );
  if (x.place_as_written)
    lines.push(
      `Placed from “${String(x.place_as_written)}” (${String(x.place_level ?? "place")}).`,
    );
  if (x.alert_level) lines.push(`GDACS alert level: ${String(x.alert_level)}.`);
  if (Array.isArray(x.reliefweb_disaster_types) && x.reliefweb_disaster_types.length)
    lines.push(`ReliefWeb disaster type: ${x.reliefweb_disaster_types.join(", ")}.`);
  if (x.method === "entered by hand") lines.push("Entered by hand from the publisher's bulletin.");
  if (lines.length === 0) return <span className="text-muted">Not recorded</span>;
  return (
    <ul className="flex flex-col gap-1">
      {lines.map((l) => (
        <li key={l}>{l}</li>
      ))}
    </ul>
  );
}

export default async function SignalDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ entered?: string }>;
}) {
  const user = await verifySession();
  const [{ id }, { entered }] = await Promise.all([params, searchParams]);
  if (!isUuid(id)) notFound();

  let signal: Signal;
  try {
    signal = await api<Signal>(`/signals/${id}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  const reviewer = REPORT_REVIEWERS.includes(user.role);
  const [links, candidates] = reviewer
    ? await Promise.all([
        api<ReportLink[]>(`/signals/${id}/events`),
        signal.status === "dismissed"
          ? Promise.resolve([] as CandidateEvent[])
          : api<CandidateEvent[]>(`/signals/${id}/candidate-events`),
      ])
    : [[] as ReportLink[], [] as CandidateEvent[]];

  const { label: adapterLabel } = ADAPTER[signal.source.adapter];
  const located = signal.latitude !== null && signal.longitude !== null;
  const gdacs = signal.source.adapter === "gdacs";

  return (
    <>
      <PageBand
        scene="padma"
        icon={eventTypeIcon(signal.event_type)}
        back={{ href: "/signals", label: "All signals" }}
        kicker={signal.source.name}
        title={signal.title}
      >
        <div className="flex flex-wrap items-center gap-2">
          {signal.severity && (
            <span className="rounded bg-white px-0.5 py-0.5">
              <SeverityPill severity={signal.severity} />
            </span>
          )}
          <span className="rounded bg-white/15 px-2 py-0.5 text-sm">
            {signal.event_type ? eventTypeLabel(signal.event_type) : "Type not known"}
          </span>
          <span className="rounded bg-white/15 px-2 py-0.5 text-sm">
            {SOURCE_TYPE_LABEL[signal.source.source_type]}
          </span>
        </div>
      </PageBand>

      <PageBody>
        {entered && (
          <p role="status" className="rounded-md border border-ok/40 bg-brand-soft px-3 py-2">
            Bulletin saved. Link it to an event below, or create one from it.
          </p>
        )}
        <div className="grid gap-6 lg:grid-cols-[1fr_24rem] lg:items-start">
          <div className="flex min-w-0 flex-col gap-6">
            <Panel id="says" title="What it says">
              {signal.text ? (
                <p className="text-[17px] leading-relaxed whitespace-pre-wrap">{signal.text}</p>
              ) : (
                <p className="text-muted">Only the headline was published in the feed.</p>
              )}
              {signal.url && (
                <a
                  href={signal.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-4 inline-flex items-center gap-1.5 font-semibold text-brand hover:underline"
                >
                  Read the original at {signal.source.domain ?? "the source"}
                  <ExternalLink size={15} aria-hidden="true" />
                  <span className="sr-only">(opens in a new tab)</span>
                </a>
              )}
              {signal.content_policy === "excerpt" && (
                <p className="mt-3 text-sm text-muted">
                  CARCUX keeps only a short excerpt and the link; the full text stays with the
                  publisher.
                  {gdacs && " Alert data: GDACS, CC BY 4.0."}
                </p>
              )}
            </Panel>

            <Panel id="details" title="Details">
              <dl className="grid grid-cols-[8rem_1fr] gap-x-3 gap-y-2.5 text-sm">
                <dt className="text-muted">Source</dt>
                <dd>
                  {signal.source.name}, {adapterLabel.toLowerCase()}
                </dd>
                <dt className="text-muted">Published</dt>
                <dd>{formatDhaka(signal.published_at)}</dd>
                {(signal.valid_from || signal.valid_until) && (
                  <>
                    <dt className="text-muted">In effect</dt>
                    <dd>
                      {signal.valid_from ? formatDhaka(signal.valid_from) : "From publication"}
                      {" to "}
                      {signal.valid_until ? formatDhaka(signal.valid_until) : "not stated"}
                    </dd>
                  </>
                )}
                <dt className="text-muted">Place</dt>
                <dd>
                  {signal.place_name ?? "Not placed"}
                  {signal.district && signal.district !== signal.place_name && (
                    <span className="text-muted">, {signal.district} district</span>
                  )}
                  {signal.precision_m !== null && (
                    <span className="block text-muted">
                      {precisionText(signal.precision_m)} of the point below
                    </span>
                  )}
                </dd>
                {located && (
                  <>
                    <dt className="text-muted">Location</dt>
                    <dd>
                      {formatCoords(signal.latitude!, signal.longitude!)}
                      <a
                        href={`https://www.openstreetmap.org/?mlat=${signal.latitude}&mlon=${signal.longitude}#map=10/${signal.latitude}/${signal.longitude}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="ml-2 font-semibold text-brand hover:underline"
                      >
                        Open map
                      </a>
                    </dd>
                  </>
                )}
                <dt className="text-muted">Language</dt>
                <dd>{LANGUAGE_LABEL[signal.language] ?? signal.language}</dd>
                <dt className="text-muted">Collected</dt>
                <dd>
                  {formatDhaka(signal.collected_at)}
                  {signal.entered_by && `, by ${signal.entered_by.full_name}`}
                </dd>
                <dt className="text-muted">Why it is here</dt>
                <dd>
                  <HowFound signal={signal} />
                </dd>
                <dt className="text-muted">Status</dt>
                <dd className="flex flex-col items-start gap-1">
                  <SignalStatusPill status={signal.status} />
                  {signal.reviewed_by && signal.reviewed_at && (
                    <span className="text-muted">
                      By {signal.reviewed_by.full_name}, {formatDhaka(signal.reviewed_at)}
                    </span>
                  )}
                  {signal.review_note && <span>“{signal.review_note}”</span>}
                </dd>
              </dl>
            </Panel>
          </div>

          {reviewer && (
            <div className="flex flex-col gap-6">
              <Panel id="triage" title="Triage">
                <ReviewControls signalId={signal.id} status={signal.status} compact />
              </Panel>

              <Panel id="events" title="Events">
                {links.length > 0 && (
                  <ul className="mb-4 flex flex-col gap-2">
                    {links.map((l) => (
                      <li key={l.evidence_id} className="text-sm">
                        <Link
                          href={`/events/${l.event.id}?tab=evidence`}
                          className="font-semibold hover:text-brand hover:underline"
                        >
                          {l.event.title}
                        </Link>
                        <span className="text-muted"> · {relationLabel(l.relation)}</span>
                      </li>
                    ))}
                  </ul>
                )}
                {!located ? (
                  <p className="text-sm text-muted">
                    This signal has no place, so no events are suggested. Link it from an
                    event&apos;s Evidence tab instead.
                  </p>
                ) : candidates.length === 0 ? (
                  <p className="text-sm text-muted">
                    {links.length
                      ? "No other open events overlap its area and time."
                      : "No open event overlaps its area and time."}
                  </p>
                ) : (
                  <>
                    <p className="mb-3 text-sm font-semibold">Possibly about</p>
                    <ul className="flex flex-col gap-3">
                      {candidates.slice(0, 4).map((c) => (
                        <li
                          key={c.event.id}
                          className="rounded-lg border border-line bg-panel-2/50 p-3"
                        >
                          <Link
                            href={`/events/${c.event.id}`}
                            className="block leading-snug font-semibold hover:text-brand hover:underline"
                          >
                            {c.event.title}
                          </Link>
                          <p className="mb-2 text-xs text-muted">
                            {c.distance_km < 1
                              ? `${Math.round(c.distance_km * 1000)} m away`
                              : `${c.distance_km.toFixed(1)} km away`}
                            {c.same_type ? ", same type" : ""}
                          </p>
                          <LinkButtons
                            eventId={c.event.id}
                            signalId={signal.id}
                            label="Link to this event as"
                          />
                        </li>
                      ))}
                    </ul>
                  </>
                )}
                {located && signal.event_type && (
                  <Link
                    href={`/events/new?from_signal=${signal.id}`}
                    className={`${buttonSecondary} mt-4 w-full`}
                  >
                    <Plus size={16} aria-hidden="true" />
                    Create an event from it
                  </Link>
                )}
              </Panel>
            </div>
          )}
        </div>
      </PageBody>
    </>
  );
}
