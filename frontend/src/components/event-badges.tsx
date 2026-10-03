import { CircleAlert } from "lucide-react";

import {
  ASSESSMENT_STYLE,
  assessmentLabel,
  PRIORITY_STYLE,
  priorityLabel,
  statusLabel,
} from "@/lib/events";
import type { Assessment, EventStatus, EvidenceCounts, Priority } from "@/lib/types";

export function PriorityBadge({ priority }: { priority: Priority }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[13px] font-semibold whitespace-nowrap ${PRIORITY_STYLE[priority]}`}
    >
      {(priority === "critical" || priority === "high") && (
        <CircleAlert size={14} strokeWidth={2.2} aria-hidden="true" />
      )}
      {priorityLabel(priority)}
    </span>
  );
}

export function AssessmentText({ assessment }: { assessment: Assessment }) {
  return (
    <span className={`inline-flex items-center gap-1.5 ${ASSESSMENT_STYLE[assessment]}`}>
      <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-current" />
      {assessmentLabel(assessment)}
    </span>
  );
}

export function StatusText({ status }: { status: EventStatus }) {
  const tone =
    status === "active"
      ? "bg-brand-soft text-brand"
      : status === "monitoring"
        ? "bg-medium-soft text-medium"
        : "bg-panel-2 text-muted";
  return (
    <span className={`inline-flex rounded-md px-2.5 py-1 text-[13px] font-semibold ${tone}`}>
      {statusLabel(status)}
    </span>
  );
}

/** Evidence at a glance: supporting, contradicting, related, and how many people. */
export function EvidenceSummary({ counts }: { counts: EvidenceCounts }) {
  const supporting = counts.supports + counts.partially_supports;
  const total = supporting + counts.contradicts + counts.related;
  if (total === 0) return <span className="text-muted">No evidence yet</span>;
  return (
    <span className="inline-flex flex-wrap items-center gap-x-3 gap-y-1 text-muted">
      {supporting > 0 && (
        <span>
          <span className="text-ok">{supporting}</span> supporting
        </span>
      )}
      {counts.contradicts > 0 && (
        <span>
          <span className="text-critical">{counts.contradicts}</span> contradicting
        </span>
      )}
      {counts.related > 0 && (
        <span>
          <span className="text-ink">{counts.related}</span> related
        </span>
      )}
      {counts.reporters > 0 && (
        <span>
          <span className="text-ink">{counts.reporters}</span>{" "}
          {counts.reporters === 1 ? "field worker" : "field workers"}
        </span>
      )}
      {counts.signals > 0 && (
        <span>
          <span className="text-ink">{counts.signals}</span>{" "}
          {counts.signals === 1 ? "public signal" : "public signals"}
        </span>
      )}
    </span>
  );
}
