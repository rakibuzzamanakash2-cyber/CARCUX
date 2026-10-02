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
    <span className={`rounded-sm px-2 py-0.5 text-xs font-semibold ${PRIORITY_STYLE[priority]}`}>
      {priorityLabel(priority)}
    </span>
  );
}

export function AssessmentText({ assessment }: { assessment: Assessment }) {
  return <span className={ASSESSMENT_STYLE[assessment]}>{assessmentLabel(assessment)}</span>;
}

export function StatusText({ status }: { status: EventStatus }) {
  const dim = status === "resolved" || status === "dismissed";
  return <span className={dim ? "text-steel" : "text-bone"}>{statusLabel(status)}</span>;
}

/** "3 supporting · 1 contradicting · 2 field workers" */
export function EvidenceSummary({ counts }: { counts: EvidenceCounts }) {
  const supporting = counts.supports + counts.partially_supports;
  const parts: React.ReactNode[] = [];
  if (supporting) parts.push(`${supporting} supporting`);
  if (counts.contradicts)
    parts.push(
      <span key="c" className="text-signal">
        {counts.contradicts} contradicting
      </span>,
    );
  if (counts.related) parts.push(`${counts.related} related`);
  if (counts.reporters)
    parts.push(`${counts.reporters} ${counts.reporters === 1 ? "field worker" : "field workers"}`);
  if (parts.length === 0) return <span className="text-steel">No evidence yet</span>;
  return (
    <span className="text-steel">
      {parts.map((p, i) => (
        <span key={i}>
          {i > 0 && " · "}
          {p}
        </span>
      ))}
    </span>
  );
}
