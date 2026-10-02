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
      className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-semibold ${PRIORITY_STYLE[priority]}`}
    >
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
  const dim = status === "resolved" || status === "dismissed";
  return <span className={dim ? "text-muted" : "text-ink"}>{statusLabel(status)}</span>;
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
    </span>
  );
}
