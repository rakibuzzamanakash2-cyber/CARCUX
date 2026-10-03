import { CalendarDays, ExternalLink, MapPin } from "lucide-react";
import Link from "next/link";

import { Pill } from "@/components/data-table";
import { eventTypeLabel } from "@/lib/event-types";
import { formatDhaka } from "@/lib/format";
import {
  ADAPTER,
  precisionText,
  SEVERITY_STYLE,
  severityLabel,
  signalStatusLabel,
} from "@/lib/signals";
import type { Severity, Signal, SignalStatus } from "@/lib/types";

export function SeverityPill({ severity }: { severity: Severity | null }) {
  if (!severity) return <span className="text-sm text-muted">Not rated</span>;
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-bold ${SEVERITY_STYLE[severity]}`}
    >
      {severityLabel(severity)}
    </span>
  );
}

export function SignalStatusPill({ status }: { status: SignalStatus }) {
  const tone = status === "new" ? "amber" : status === "reviewed" ? "green" : "grey";
  return <Pill tone={tone}>{signalStatusLabel(status)}</Pill>;
}

/** Where a signal came from, in one line: icon, publisher, time. */
export function SourceLine({ signal }: { signal: Signal }) {
  const { icon: Icon } = ADAPTER[signal.source.adapter];
  return (
    <span className="inline-flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted">
      <span className="inline-flex items-center gap-1.5 font-semibold text-ink">
        <Icon size={15} aria-hidden="true" className="text-brand" />
        {signal.source.name}
      </span>
      <span className="inline-flex items-center gap-1.5">
        <CalendarDays size={14} aria-hidden="true" />
        {formatDhaka(signal.published_at)}
      </span>
      {signal.place_name && (
        <span
          className="inline-flex items-center gap-1.5"
          title={precisionText(signal.precision_m)}
        >
          <MapPin size={14} aria-hidden="true" />
          {signal.place_name}
        </span>
      )}
      {signal.event_type && <span>{eventTypeLabel(signal.event_type)}</span>}
    </span>
  );
}

/** A signal as evidence or a suggestion: source line, headline, excerpt, link out. */
export function SignalSummary({ signal }: { signal: Signal }) {
  return (
    <div className="flex flex-col gap-1">
      <SourceLine signal={signal} />
      <p className="flex flex-wrap items-center gap-2">
        <Link
          href={`/signals/${signal.id}`}
          className="font-semibold hover:text-brand hover:underline"
        >
          {signal.title}
        </Link>
        {signal.severity && <SeverityPill severity={signal.severity} />}
      </p>
      {signal.text && <p className="line-clamp-2 text-sm text-muted">{signal.text}</p>}
      {signal.url && (
        <a
          href={signal.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex w-fit items-center gap-1 text-sm font-semibold text-brand hover:underline"
        >
          Read at {signal.source.domain ?? "source"}
          <ExternalLink size={13} aria-hidden="true" />
          <span className="sr-only">(opens in a new tab)</span>
        </a>
      )}
    </div>
  );
}
