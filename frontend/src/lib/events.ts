/** Labels, meanings and colours for event fields. Shared by server and client components. */
import type {
  Assessment,
  ClaimAttribute,
  EventStatus,
  EvidenceRelation,
  GroundTruthKind,
  Priority,
} from "@/lib/types";

export const STATUSES: { value: EventStatus; label: string; meaning: string }[] = [
  { value: "active", label: "Active", meaning: "Happening now and needs attention." },
  { value: "monitoring", label: "Monitoring", meaning: "Easing, but still being watched." },
  { value: "resolved", label: "Resolved", meaning: "Over." },
  {
    value: "dismissed",
    label: "Dismissed",
    meaning: "Not a real event: a duplicate, a mistake, or refuted.",
  },
];

export const PRIORITIES: { value: Priority; label: string }[] = [
  { value: "critical", label: "Critical" },
  { value: "high", label: "High" },
  { value: "medium", label: "Medium" },
  { value: "low", label: "Low" },
];

/** The dataset's assessment labels, with its definitions (common.schema.json). */
export const ASSESSMENTS: { value: Assessment; label: string; meaning: string }[] = [
  {
    value: "verified",
    label: "Verified",
    meaning: "The evidence establishes it happened as described.",
  },
  {
    value: "partially_verified",
    label: "Partially verified",
    meaning: "It happened, but key details are uncertain or disputed.",
  },
  {
    value: "conflicting",
    label: "Conflicting",
    meaning: "Credible evidence on both sides of whether it happened.",
  },
  {
    value: "unverified",
    label: "Unverified",
    meaning: "Claims exist, but none independent or credible enough yet.",
  },
  {
    value: "refuted",
    label: "Refuted",
    meaning: "The evidence establishes it did not happen, or not as claimed.",
  },
  {
    value: "insufficient_evidence",
    label: "Insufficient evidence",
    meaning: "Too little information to judge.",
  },
];

export const RELATIONS: { value: EvidenceRelation; label: string; short: string }[] = [
  { value: "supports", label: "Supports", short: "supports" },
  { value: "partially_supports", label: "Partly supports", short: "partly supports" },
  { value: "contradicts", label: "Contradicts", short: "contradicts" },
  { value: "related", label: "Related only", short: "related" },
];

const find = <T extends { value: string; label: string }>(list: T[], value: string) =>
  list.find((x) => x.value === value);

export const statusLabel = (v: EventStatus) => find(STATUSES, v)?.label ?? v;
export const priorityLabel = (v: Priority) => find(PRIORITIES, v)?.label ?? v;
export const assessmentLabel = (v: Assessment) => find(ASSESSMENTS, v)?.label ?? v;
export const relationLabel = (v: EvidenceRelation) => find(RELATIONS, v)?.label ?? v;

/** Red is a signal: only critical priority and refuted/conflicting assessments use it. */
export const PRIORITY_STYLE: Record<Priority, string> = {
  critical: "bg-critical-soft text-critical ring-1 ring-critical/30",
  high: "bg-alert-soft text-alert ring-1 ring-alert/30",
  medium: "bg-medium-soft text-medium ring-1 ring-medium/25",
  low: "bg-panel-2 text-muted ring-1 ring-line",
};

export const ASSESSMENT_STYLE: Record<Assessment, string> = {
  verified: "text-ok",
  partially_verified: "text-ok",
  conflicting: "text-alert",
  unverified: "text-alert",
  refuted: "text-critical",
  insufficient_evidence: "text-muted",
};

export const RELATION_STYLE: Record<EvidenceRelation, string> = {
  supports: "border-l-ok",
  partially_supports: "border-l-ok/50",
  contradicts: "border-l-critical",
  related: "border-l-muted/40",
};

export const FAMILIES = [
  { value: "natural_calamity", label: "Natural calamity" },
  { value: "road_infrastructure", label: "Road and infrastructure" },
  { value: "urban_emergency", label: "Urban emergency" },
] as const;

export const familyLabel = (v: string) => FAMILIES.find((f) => f.value === v)?.label ?? v;

/** Marker colours on the map, by priority. */
export const PRIORITY_COLOR: Record<Priority, string> = {
  critical: "#ef3b42",
  high: "#f2912c",
  medium: "#3f8ef0",
  low: "#9aaba2",
};

/** Marker shapes on the map, by family: easy to tell apart without colour. */
export const FAMILY_SHAPE: Record<string, "circle" | "diamond" | "triangle"> = {
  natural_calamity: "circle",
  road_infrastructure: "diamond",
  urban_emergency: "triangle",
};

/** What an item can get wrong about an event (dataset claim attributes), in plain words. */
export const CLAIM_ATTRIBUTES: { value: ClaimAttribute; label: string }[] = [
  { value: "location", label: "Place" },
  { value: "start_time", label: "When it started" },
  { value: "end_time", label: "When it ended" },
  { value: "status", label: "Whether it is still going on" },
  { value: "magnitude", label: "How bad (depth, size)" },
  { value: "affected_count", label: "Number affected" },
  { value: "casualty_count", label: "Deaths or injuries" },
  { value: "cause", label: "Cause" },
  { value: "event_type", label: "Kind of event" },
];

export const claimLabel = (v: ClaimAttribute) =>
  CLAIM_ATTRIBUTES.find((a) => a.value === v)?.label ?? v;

export const CONFIDENCE: { value: 1 | 2 | 3; label: string }[] = [
  { value: 1, label: "Unsure" },
  { value: 2, label: "Fairly sure" },
  { value: 3, label: "Certain" },
];

export const GROUND_TRUTH_KINDS: { value: GroundTruthKind; label: string }[] = [
  { value: "official", label: "Official statement" },
  { value: "news_followup", label: "Follow-up news report" },
  { value: "humanitarian_report", label: "Humanitarian situation report" },
  { value: "other", label: "Other" },
];
