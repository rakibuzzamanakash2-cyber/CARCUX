export type Role = "admin" | "analyst" | "field_worker" | "viewer";

export const ROLES: { value: Role; label: string; description: string }[] = [
  { value: "admin", label: "Admin", description: "Manages accounts and settings" },
  { value: "analyst", label: "Analyst", description: "Reviews events, verifies assessments" },
  { value: "field_worker", label: "Field worker", description: "Submits field reports" },
  { value: "viewer", label: "Viewer", description: "Read-only dashboard access" },
];

export function roleLabel(role: Role): string {
  return ROLES.find((r) => r.value === role)?.label ?? role;
}

/** Mirrors the backend's UserRead schema. */
export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface Health {
  status: string;
  service: string;
  version: string;
  environment: string;
}

/** Result shape returned by Server Actions to forms. */
export type ActionState = { ok: boolean; message: string } | undefined;

/** Mirrors the backend's field report schemas. */
export interface IntegrityFlag {
  code: string;
  detail: string;
}

export interface ReportMedia {
  id: string;
  position: number;
  content_type: string;
  size_bytes: number;
  width: number;
  height: number;
  sha256: string;
}

export interface FieldReport {
  id: string;
  client_report_id: string;
  reporter: { id: string; full_name: string };
  text: string;
  event_type: string | null;
  place_name: string | null;
  latitude: number;
  longitude: number;
  location_accuracy_m: number | null;
  observed_at: string;
  received_at: string;
  status: "submitted" | "reviewed" | "dismissed";
  content_hash: string;
  integrity_flags: IntegrityFlag[];
  media: ReportMedia[];
  reviewed_by: { id: string; full_name: string } | null;
  reviewed_at: string | null;
  review_note: string | null;
}

export type ReportStatus = FieldReport["status"];

export interface FieldReportPage {
  items: FieldReport[];
  total: number;
  limit: number;
  offset: number;
}

export interface VerifyResult {
  report_id: string;
  intact: boolean;
  problems: string[];
  content_hash: string;
}

/** Roles that may read field reports, and roles that may submit them. */
export const REPORT_READERS: Role[] = ["field_worker", "analyst", "admin"];
export const REPORT_SUBMITTERS: Role[] = ["field_worker", "admin"];
export const REPORT_REVIEWERS: Role[] = ["analyst", "admin"];

/** Mirrors the backend's event schemas. */
export type EventStatus = "active" | "monitoring" | "resolved" | "dismissed";
export type Priority = "low" | "medium" | "high" | "critical";
export type Assessment =
  | "verified"
  | "partially_verified"
  | "conflicting"
  | "unverified"
  | "refuted"
  | "insufficient_evidence";
export type EvidenceRelation = "supports" | "partially_supports" | "contradicts" | "related";

export interface EvidenceCounts {
  supports: number;
  partially_supports: number;
  contradicts: number;
  related: number;
  reporters: number;
  photos: number;
  signals: number;
}

export interface CarcuxEvent {
  id: string;
  title: string;
  summary: string | null;
  event_type: string;
  family: string;
  status: EventStatus;
  priority: Priority;
  assessment: Assessment;
  place_name: string | null;
  latitude: number;
  longitude: number;
  started_at: string;
  ended_at: string | null;
  created_by: { id: string; full_name: string };
  created_at: string;
  updated_at: string;
  evidence_counts: EvidenceCounts;
}

export interface EventPage {
  items: CarcuxEvent[];
  total: number;
  limit: number;
  offset: number;
}

export interface Evidence {
  id: string;
  relation: EvidenceRelation;
  note: string | null;
  linked_by: { id: string; full_name: string };
  linked_at: string;
  /** Exactly one of these is set. */
  field_report: FieldReport | null;
  signal: Signal | null;
}

export interface CandidateReport {
  report: FieldReport;
  distance_km: number;
  hours_apart: number;
  same_type: boolean;
}

export interface CandidateEvent {
  event: CarcuxEvent;
  distance_km: number;
  hours_apart: number;
  same_type: boolean;
  same_family: boolean;
}

export interface ReportLink {
  evidence_id: string;
  relation: EvidenceRelation;
  event: CarcuxEvent;
}

export interface HistoryEntry {
  occurred_at: string;
  action: string;
  actor: { id: string; full_name: string } | null;
  details: Record<string, unknown>;
}

export interface Overview {
  as_of: string;
  open_events: number;
  open_by_priority: Record<Priority, number>;
  reports_24h: number;
  flagged_24h: number | null;
  unreviewed_reports: number | null;
  signals_24h: number;
  unreviewed_signals: number | null;
}

export interface AuditEntry {
  id: number;
  occurred_at: string;
  action: string;
  actor: { id: string; full_name: string } | null;
  target_type: string | null;
  target_id: string | null;
  ip_address: string | null;
  details: Record<string, unknown>;
}

export interface AuditPage {
  items: AuditEntry[];
  total: number;
  limit: number;
  offset: number;
  actions: string[];
}

/** Mirrors the backend's signal and source schemas. */
export type SourceType = "news" | "public_record" | "other";
export type SourceAdapter = "gdacs" | "rss" | "reliefweb" | "manual";
export type SignalStatus = "new" | "reviewed" | "dismissed";
export type Severity = "minor" | "moderate" | "severe";

export interface SourceBrief {
  id: string;
  key: string;
  name: string;
  source_type: SourceType;
  adapter: SourceAdapter;
  domain: string | null;
}

export interface Source extends SourceBrief {
  url: string | null;
  language: string;
  enabled: boolean;
  interval_minutes: number;
  last_run_at: string | null;
  last_success_at: string | null;
  last_error: string | null;
  signal_count: number;
  signals_24h: number;
}

export interface IngestRun {
  id: string;
  started_at: string;
  finished_at: string | null;
  ok: boolean;
  fetched: number;
  created: number;
  updated: number;
  skipped: number;
  error: string | null;
}

export interface Signal {
  id: string;
  source: SourceBrief;
  external_id: string;
  title: string;
  text: string | null;
  content_policy: "full" | "excerpt" | "reference_only";
  url: string | null;
  language: string;
  event_type: string | null;
  family: string | null;
  severity: Severity | null;
  place_name: string | null;
  district: string | null;
  latitude: number | null;
  longitude: number | null;
  precision_m: number | null;
  published_at: string;
  valid_from: string | null;
  valid_until: string | null;
  collected_at: string;
  updated_at: string;
  extraction: Record<string, unknown>;
  status: SignalStatus;
  reviewed_by: { id: string; full_name: string } | null;
  reviewed_at: string | null;
  review_note: string | null;
  entered_by: { id: string; full_name: string } | null;
}

export interface SignalPage {
  items: Signal[];
  total: number;
  limit: number;
  offset: number;
}

export interface CandidateSignal {
  signal: Signal;
  distance_km: number;
  hours_apart: number;
  same_type: boolean;
}

export interface District {
  name: string;
  division: string;
  latitude: number;
  longitude: number;
}
