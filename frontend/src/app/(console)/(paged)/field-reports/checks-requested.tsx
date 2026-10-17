import { CalendarDays, MapPin, Send } from "lucide-react";
import Link from "next/link";

import { Panel } from "@/components/page-header";
import { eventTypeIcon } from "@/lib/event-icons";
import { eventTypeLabel } from "@/lib/event-types";
import { formatCoords, formatDhaka } from "@/lib/format";
import type { RequestForWorkers } from "@/lib/types";

/** Open requests from analysts to go and check a place. Shown to field workers; only
 * what to check and where, so that what they report is what they see. */
export function ChecksRequested({ requests }: { requests: RequestForWorkers[] }) {
  if (requests.length === 0) return null;
  return (
    <Panel
      id="checks"
      title={`Checks requested (${requests.length})`}
      description="Analysts need someone to look. If you are near, go and report what you see, even if nothing is happening there: that is just as useful."
    >
      <ul className="flex flex-col divide-y divide-line">
        {requests.map((r) => {
          const TypeIcon = eventTypeIcon(r.event_type);
          return (
            <li
              key={r.id}
              className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="flex flex-col gap-1">
                <p className="font-semibold">{r.question}</p>
                <p className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted">
                  <span className="inline-flex items-center gap-1.5">
                    <TypeIcon size={15} aria-hidden="true" />
                    {eventTypeLabel(r.event_type)}
                  </span>
                  <a
                    className="inline-flex items-center gap-1.5 hover:underline"
                    href={`https://www.openstreetmap.org/?mlat=${r.latitude}&mlon=${r.longitude}#map=16/${r.latitude}/${r.longitude}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <MapPin size={15} aria-hidden="true" />
                    {r.place_name ?? formatCoords(r.latitude, r.longitude)}
                  </a>
                  <span className="inline-flex items-center gap-1.5">
                    <CalendarDays size={15} aria-hidden="true" />
                    Asked {formatDhaka(r.created_at)}
                  </span>
                  {r.answered_by_me > 0 && (
                    <span className="font-semibold text-ok">
                      You answered {r.answered_by_me === 1 ? "once" : `${r.answered_by_me} times`}
                    </span>
                  )}
                </p>
              </div>
              <Link
                href={`/field-reports/new?request=${r.id}`}
                className="inline-flex shrink-0 items-center justify-center gap-2 rounded-md bg-water px-4 py-2 text-sm font-semibold text-white hover:bg-brand-strong"
              >
                <Send size={15} aria-hidden="true" />
                {r.answered_by_me > 0 ? "Report again" : "Report what you see"}
              </Link>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}
