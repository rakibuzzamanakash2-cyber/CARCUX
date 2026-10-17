import { ArrowDown, ArrowUp, CalendarDays, Crosshair, Inbox, MapPin, Send } from "lucide-react";
import Link from "next/link";
import { createElement } from "react";

import { AssessmentText, PriorityBadge } from "@/components/event-badges";
import { PageBand, PageBody, Panel, Tabs } from "@/components/page-header";
import { api } from "@/lib/api";
import { requireRole } from "@/lib/dal";
import { eventTypeIcon } from "@/lib/event-icons";
import { eventTypeLabel } from "@/lib/event-types";
import { statusLabel } from "@/lib/events";
import { formatDhaka, percent } from "@/lib/format";
import {
  REPORT_REVIEWERS,
  type FieldReportPage,
  type EventQueueItem,
  type EventQueuePage,
} from "@/lib/types";

export const metadata = { title: "Events to check" };

/** How much a check is needed, as a bar: need runs from 0 to 1. */
function NeedBar({ need }: { need: number }) {
  const width = Math.max(4, Math.round(need * 100));
  const tone = need >= 0.66 ? "bg-critical" : need >= 0.33 ? "bg-amber" : "bg-ok";
  return (
    <div className="flex items-center gap-2" title={`Need for a check: ${percent(need)}`}>
      <div className="h-2 w-24 overflow-hidden rounded-full bg-panel-2" aria-hidden="true">
        <div className={`h-full ${tone}`} style={{ width: `${width}%` }} />
      </div>
      <span className="text-xs text-muted">need {Math.round(need * 100)} / 100</span>
    </div>
  );
}

function Item({ item, rank }: { item: EventQueueItem; rank: number }) {
  const e = item.event;
  const v = item.value;
  return (
    <li className="overflow-hidden rounded-xl border border-line bg-panel shadow-sm">
      <div className="grid gap-4 p-4 md:p-5 lg:grid-cols-[1fr_20rem]">
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted">
            <span className="font-mono text-xs">#{rank}</span>
            <PriorityBadge priority={e.priority} />
            <span>{statusLabel(e.status)}</span>
            <span className="inline-flex items-center gap-1.5">
              {createElement(eventTypeIcon(e.event_type), { size: 15, "aria-hidden": true })}
              {eventTypeLabel(e.event_type)}
            </span>
            {e.place_name && (
              <span className="inline-flex items-center gap-1.5">
                <MapPin size={15} aria-hidden="true" />
                {e.place_name}
              </span>
            )}
            <span className="inline-flex items-center gap-1.5">
              <CalendarDays size={15} aria-hidden="true" />
              {formatDhaka(e.started_at)}
            </span>
          </div>
          <Link
            href={`/events/${e.id}#check`}
            className="text-lg leading-snug font-semibold text-ink hover:text-brand hover:underline"
          >
            {e.title}
          </Link>
          <ul className="flex list-disc flex-col gap-0.5 pl-5 text-sm">
            {item.reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </div>
        <div className="flex flex-col gap-3 rounded-lg bg-panel-2 p-3 text-sm">
          <NeedBar need={item.need} />
          <div>
            <span className="text-muted">Team: </span>
            <AssessmentText assessment={e.assessment} />
            {item.differs && (
              <>
                <span className="text-muted"> · evidence suggests </span>
                <AssessmentText assessment={item.suggested} />
              </>
            )}
          </div>
          {v.probability !== null ? (
            <div className="flex flex-col gap-0.5">
              <span>
                <strong>{percent(v.probability)}</strong> likely it happened
              </span>
              <span className="inline-flex items-center gap-1.5 text-muted">
                <ArrowUp size={14} aria-hidden="true" /> {percent(v.if_supported)} if a check says
                yes
              </span>
              <span className="inline-flex items-center gap-1.5 text-muted">
                <ArrowDown size={14} aria-hidden="true" /> {percent(v.if_denied)} if it says no
              </span>
            </div>
          ) : (
            <span className="text-muted">No evidence linked yet.</span>
          )}
          {item.open_request ? (
            <span className="inline-flex items-center gap-1.5 font-semibold text-water">
              <Send size={14} aria-hidden="true" />
              Check requested · {item.open_request.responses}{" "}
              {item.open_request.responses === 1 ? "answer" : "answers"}
            </span>
          ) : (
            <Link
              href={`/events/${e.id}#check`}
              className="inline-flex items-center gap-1.5 font-semibold text-brand hover:underline"
            >
              <Send size={14} aria-hidden="true" />
              Request more evidence
            </Link>
          )}
        </div>
      </div>
    </li>
  );
}

export default async function EventsToCheckPage() {
  await requireRole(...REPORT_REVIEWERS);
  const [queue, waiting] = await Promise.all([
    api<EventQueuePage>("/review-queue?limit=50"),
    api<FieldReportPage>("/field-reports?status=submitted&limit=1"),
  ]);

  return (
    <>
      <PageBand
        scene="hills"
        icon={Crosshair}
        title="Events to check"
        description="Open events, the ones where a check matters most first: the priority your team set, times how uncertain the event is and how likely one more field report is to change its assessment."
      />
      <PageBody>
        <Tabs
          active="events"
          items={[
            {
              key: "reports",
              label: "Field reports",
              href: "/review",
              icon: Inbox,
              count: waiting.total,
            },
            {
              key: "events",
              label: "Events to check",
              href: "/review/events",
              icon: Crosshair,
              count: queue.total,
            },
          ]}
        />
        {queue.items.length === 0 ? (
          <Panel>
            <p className="py-8 text-center text-muted">No open events. Nothing to check.</p>
          </Panel>
        ) : (
          <ol className="flex flex-col gap-4" aria-label="Events, most in need of a check first">
            {queue.items.map((item, i) => (
              <Item key={item.event.id} item={item} rank={i + 1} />
            ))}
          </ol>
        )}
        <p className="text-sm text-muted">
          A ranking aid, not a decision: an event low on the list can still matter. Need is the
          average of how uncertain the event is (highest at 50%) and the chance one more field
          report changes its assessment (verified at 80% or more, refuted at 20% or less).
          {queue.total > queue.items.length &&
            ` Showing the first ${queue.items.length} of ${queue.total}.`}
        </p>
      </PageBody>
    </>
  );
}
