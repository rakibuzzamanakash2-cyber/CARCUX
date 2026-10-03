import { Ban, CalendarDays, Clock, Flag, Hourglass, Inbox, MapPin, Plus } from "lucide-react";
import Link from "next/link";

import { Initials, Pill } from "@/components/data-table";
import { LinkButtons } from "@/components/evidence-controls";
import { FilterBar } from "@/components/filter-bar";
import {
  buttonSecondary,
  PageBand,
  PageBody,
  Panel,
  StatTile,
  StatTiles,
} from "@/components/page-header";
import { Pager } from "@/components/pager";
import { ReviewControls } from "@/components/review-controls";
import { api } from "@/lib/api";
import { requireRole } from "@/lib/dal";
import { eventTypeIcon } from "@/lib/event-icons";
import { eventTypeLabel } from "@/lib/event-types";
import { FLAG_INFO, flagLabel, formatDhaka } from "@/lib/format";
import { REPORT_REVIEWERS, type CandidateEvent, type FieldReportPage } from "@/lib/types";

export const metadata = { title: "Review queue" };

const PAGE_SIZE = 10;

function href(flagged: boolean, page = 1): string {
  const p = new URLSearchParams();
  if (flagged) p.set("flagged", "1");
  if (page > 1) p.set("page", String(page));
  const q = p.toString();
  return q ? `/review?${q}` : "/review";
}

/** How long the oldest report has been waiting, in words. */
function waiting(iso: string | undefined): string {
  if (!iso) return "Nothing waiting";
  const hours = Math.floor((Date.now() - new Date(iso).getTime()) / 3_600_000);
  if (hours < 1) return "Under an hour";
  if (hours < 48) return `${hours} ${hours === 1 ? "hour" : "hours"}`;
  return `${Math.floor(hours / 24)} days`;
}

export default async function ReviewPage({
  searchParams,
}: {
  searchParams: Promise<{ flagged?: string; page?: string }>;
}) {
  await requireRole(...REPORT_REVIEWERS);
  const params = await searchParams;
  const flagged = params.flagged === "1";
  const page = Math.max(1, Number.parseInt(params.page ?? "1", 10) || 1);

  const query = new URLSearchParams({
    status: "submitted",
    order: "oldest",
    limit: String(PAGE_SIZE),
    offset: String((page - 1) * PAGE_SIZE),
  });
  if (flagged) query.set("flagged", "true");

  const [queue, flaggedWaiting, dismissed, oldest] = await Promise.all([
    api<FieldReportPage>(`/field-reports?${query}`),
    api<FieldReportPage>("/field-reports?status=submitted&flagged=true&limit=1"),
    api<FieldReportPage>("/field-reports?status=dismissed&limit=1"),
    api<FieldReportPage>("/field-reports?status=submitted&order=oldest&limit=1"),
  ]);
  // Suggested events for each report on this page (5 km, 48 h; suggestions only).
  const suggestions = await Promise.all(
    queue.items.map((r) => api<CandidateEvent[]>(`/field-reports/${r.id}/candidate-events`)),
  );
  const lastPage = Math.max(1, Math.ceil(queue.total / PAGE_SIZE));
  const totalWaiting = flagged ? oldest.total : queue.total;

  return (
    <>
      <PageBand
        scene="hills"
        icon={Inbox}
        title="Review queue"
        description="Field reports nobody has looked at yet, oldest first. Place each against an event, mark it reviewed, or dismiss it with a reason."
      />
      <PageBody>
        <StatTiles>
          <StatTile
            icon={Inbox}
            value={totalWaiting}
            label="Waiting"
            note="Not yet reviewed"
            tone="amber"
            href={href(false)}
          />
          <StatTile
            icon={Flag}
            value={flaggedWaiting.total}
            label="Flagged and waiting"
            note="Look at these first"
            tone="red"
            href={href(true)}
          />
          <StatTile
            icon={Hourglass}
            value={waiting(oldest.items[0]?.received_at)}
            label="Oldest waiting"
            note="Since it arrived"
            tone="blue"
          />
          <StatTile
            icon={Ban}
            value={dismissed.total}
            label="Dismissed"
            note="Since the start"
            tone="green"
          />
        </StatTiles>

        <FilterBar
          action="/review"
          selects={[
            {
              name: "flagged",
              label: "Show",
              value: flagged ? "1" : "",
              options: [
                { value: "", label: "Everything waiting" },
                { value: "1", label: "Flagged only" },
              ],
            },
          ]}
        />

        {queue.items.length === 0 ? (
          <Panel>
            <p className="py-8 text-center text-muted">
              {flagged
                ? "No flagged reports are waiting."
                : "The queue is empty. Every report has been looked at."}
            </p>
          </Panel>
        ) : (
          <ol className="flex flex-col gap-4" aria-label="Reports waiting for review">
            {queue.items.map((r, i) => {
              const TypeIcon = eventTypeIcon(r.event_type);
              const candidates = suggestions[i];
              return (
                <li
                  key={r.id}
                  className={`overflow-hidden rounded-xl border bg-panel shadow-sm ${
                    r.integrity_flags.length ? "border-critical/40" : "border-line"
                  }`}
                >
                  <div className="grid lg:grid-cols-[1fr_22rem]">
                    <div className="flex flex-col gap-3 p-4 md:p-5">
                      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted">
                        <span className="inline-flex items-center gap-1.5">
                          <CalendarDays size={15} aria-hidden="true" className="text-brand" />
                          Seen {formatDhaka(r.observed_at)}
                        </span>
                        <span className="inline-flex items-center gap-1.5">
                          <Clock size={15} aria-hidden="true" />
                          Arrived {formatDhaka(r.received_at)}
                        </span>
                        <span className="inline-flex items-center gap-2">
                          <Initials name={r.reporter.full_name} />
                          {r.reporter.full_name}
                        </span>
                      </div>
                      <Link
                        href={`/field-reports/${r.id}`}
                        className="text-lg leading-snug font-semibold text-ink hover:text-brand hover:underline"
                      >
                        {r.text}
                      </Link>
                      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted">
                        <span className="inline-flex items-center gap-1.5">
                          <TypeIcon size={15} aria-hidden="true" />
                          {eventTypeLabel(r.event_type)}
                        </span>
                        {r.place_name && (
                          <span className="inline-flex items-center gap-1.5">
                            <MapPin size={15} aria-hidden="true" />
                            {r.place_name}
                          </span>
                        )}
                        <span>
                          {r.media.length} {r.media.length === 1 ? "photo" : "photos"}
                        </span>
                      </div>
                      {r.media.length > 0 && (
                        <div className="flex gap-2">
                          {r.media.slice(0, 3).map((m) => (
                            // Authenticated, uncached photo: next/image would cache it.
                            // eslint-disable-next-line @next/next/no-img-element
                            <img
                              key={m.id}
                              src={`/field-reports/${r.id}/photos/${m.id}`}
                              alt={`Photo ${m.position + 1} from this report`}
                              loading="lazy"
                              className="h-20 w-28 rounded-lg border border-line bg-panel-2 object-cover"
                            />
                          ))}
                        </div>
                      )}
                      {r.integrity_flags.length > 0 && (
                        <ul className="flex flex-col gap-1.5">
                          {r.integrity_flags.map((f, j) => (
                            <li
                              key={`${f.code}-${j}`}
                              className="flex flex-wrap items-start gap-2 text-sm"
                            >
                              <Pill tone="red">
                                <Flag size={13} aria-hidden="true" />
                                {flagLabel(f.code)}
                              </Pill>
                              <span className="text-muted">
                                {FLAG_INFO[f.code]?.meaning ?? f.detail}
                              </span>
                            </li>
                          ))}
                        </ul>
                      )}
                      <ReviewControls reportId={r.id} status={r.status} />
                    </div>

                    <div className="flex flex-col gap-3 border-t border-line bg-panel-2/60 p-4 lg:border-t-0 lg:border-l md:p-5">
                      <p className="text-sm font-semibold">Possibly the same situation</p>
                      {candidates.length === 0 ? (
                        <p className="text-sm text-muted">
                          No open event within 5 km and 48 hours.
                        </p>
                      ) : (
                        <ul className="flex flex-col gap-3">
                          {candidates.slice(0, 3).map((c) => (
                            <li
                              key={c.event.id}
                              className="rounded-lg border border-line bg-panel p-3"
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
                                reportId={r.id}
                                label="Link to this event as"
                              />
                            </li>
                          ))}
                        </ul>
                      )}
                      <Link
                        href={`/events/new?from_report=${r.id}`}
                        className={`${buttonSecondary} mt-auto`}
                      >
                        <Plus size={16} aria-hidden="true" />
                        Create an event from it
                      </Link>
                    </div>
                  </div>
                </li>
              );
            })}
          </ol>
        )}

        {queue.total > PAGE_SIZE && (
          <Pager
            page={page}
            lastPage={lastPage}
            total={queue.total}
            noun="reports waiting"
            labels={["Earlier", "Later"]}
            newer={page > 1 ? href(flagged, page - 1) : null}
            older={page < lastPage ? href(flagged, page + 1) : null}
          />
        )}
      </PageBody>
    </>
  );
}
