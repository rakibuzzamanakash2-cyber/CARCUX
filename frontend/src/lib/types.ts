export type Role = "admin" | "analyst" | "field_worker" | "viewer" | "official";

export const ROLES: { value: Role; label: string; description: string }[] = [
  { value: "admin", label: "Admin", description: "Manages accounts and settings" },
  { value: "analyst", label: "Analyst", description: "Reviews events, verifies assessments" },
  { value: "field_worker", label: "Field worker", description: "Submits field reports" },
  { value: "viewer", label: "Viewer", description: "Read-only dashboard access" },
  {
    value: "official",
    label: "Official",
    description: "Speaks for one verified official page",
  },
];

/** Roles chosen on the Users page; officials are added from their official page. */
export const STAFF_ROLES = ROLES.filter((r) => r.value !== "official");

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
  official_page?: { id: string; slug: string; name: string; status: PageStatus } | null;
}

export type PageKind =
  | "head_of_government"
  | "ministry"
  | "department"
  | "city_corporation"
  | "district_administration"
  | "member_of_parliament"
  | "agency";
export type PageStatus = "pending" | "verified" | "suspended";
export type VerificationMethod = "official_email" | "official_letter";

export const PAGE_KINDS: { value: PageKind; label: string }[] = [
  { value: "head_of_government", label: "Head of government (PMO)" },
  { value: "ministry", label: "Ministry" },
  { value: "department", label: "Division or department" },
  { value: "city_corporation", label: "City corporation" },
  { value: "district_administration", label: "District administration" },
  { value: "member_of_parliament", label: "Member of parliament" },
  { value: "agency", label: "Public agency" },
];

export const pageKindLabel = (k: PageKind) => PAGE_KINDS.find((x) => x.value === k)?.label ?? k;

export const VERIFICATION_LABEL: Record<VerificationMethod, string> = {
  official_email: "confirmed from the office's own email address",
  official_letter: "official letter on file",
};

/** What everyone signed in sees of an official page. */
export interface OfficialPage {
  id: string;
  slug: string;
  name: string;
  name_bn: string | null;
  kind: PageKind;
  description: string | null;
  website: string | null;
  status: PageStatus;
  verification_method: VerificationMethod | null;
  verified_at: string | null;
}

/** Admins and the page's own officials also see how it was verified. */
export interface OfficialPageDetail extends OfficialPage {
  contact_email: string | null;
  verification_note: string | null;
  verified_by: { id: string; full_name: string } | null;
  has_document: boolean;
  document_type: string | null;
  document_sha256: string | null;
  suspended_reason: string | null;
  created_at: string;
  members: {
    id: string;
    full_name: string;
    email: string;
    is_active: boolean;
    last_login_at: string | null;
  }[];
}

export type Finding = "confirmed" | "partly_confirmed" | "denied" | "under_review";

export const FINDINGS: { value: Finding; label: string; description: string }[] = [
  { value: "confirmed", label: "Confirmed", description: "It happened as reported." },
  {
    value: "partly_confirmed",
    label: "Partly confirmed",
    description: "It happened, but not as reported (place, toll, cause…).",
  },
  { value: "denied", label: "Denied", description: "It did not happen." },
  { value: "under_review", label: "Under review", description: "Being checked; no finding yet." },
];

export const findingLabel = (f: Finding) => FINDINGS.find((x) => x.value === f)?.label ?? f;

/** CARCUX's brief on an event, as an official sees it (field workers unnamed). */
export interface Brief {
  generated_at: string;
  event: {
    id: string;
    title: string;
    summary: string | null;
    event_type: string;
    place_name: string | null;
    started_at: string;
    ended_at: string | null;
    status: EventStatus;
    assessment: Assessment;
    evidence_counts: EvidenceCounts;
  };
  suggestion: {
    label: Assessment;
    probability: number | null;
    method: "start" | "model";
    sources_supporting: number;
    sources_denying: number;
    credible_supporting: number;
    credible_denying: number;
    disputed: string[];
    counted_once: number;
  };
  details: {
    attribute: ClaimAttribute;
    estimate: string | number | null;
    unit: string | null;
    disputed: boolean;
    sources: number;
    values: string[];
  }[];
  sources: {
    source: string;
    kind: string;
    says: "happened" | "did not happen" | "unclear";
    reliability: number;
    disputes: string[];
  }[];
  field_workers: number;
}

export interface Statement {
  id: string;
  page: {
    id: string;
    slug: string;
    name: string;
    name_bn: string | null;
    kind: PageKind;
    status: PageStatus;
  };
  event: {
    id: string;
    title: string;
    event_type: string;
    place_name: string | null;
    started_at: string;
  };
  finding: Finding;
  title: string;
  body: string;
  published_at: string;
  informed_by_carcux: boolean;
  supersedes_id: string | null;
  superseded_by_id: string | null;
  author: string | null;
}

export interface StatementDetail extends Statement {
  brief: Brief;
}

/** The public site. */
export interface PublicMe {
  id: string;
  display_name: string;
  email: string;
}

export interface PublicComment {
  id: string;
  author: string;
  body: string;
  created_at: string;
  mine: boolean;
}

export interface PublicPost {
  id: string;
  page: Statement["page"];
  event: Statement["event"];
  finding: Finding;
  title: string;
  body: string;
  published_at: string;
  supersedes_id: string | null;
  superseded_by_id: string | null;
  likes: number;
  comments: number;
  liked: boolean;
}

export interface PublicPostDetail extends PublicPost {
  comment_list: PublicComment[];
}

export interface PublicPageView {
  page: Statement["page"];
  description: string | null;
  website: string | null;
  verified_at: string | null;
  posts: PublicPost[];
}

export interface PublicIncident {
  event: Statement["event"];
  posts: PublicPost[];
}

export const REPORT_REASONS: { value: string; label: string }[] = [
  { value: "false_information", label: "False information" },
  { value: "abuse", label: "Abuse or hate" },
  { value: "spam", label: "Spam" },
  { value: "personal_information", label: "Shares someone's personal information" },
  { value: "other", label: "Something else" },
];

export interface ModerationComment {
  id: string;
  statement_id: string;
  statement_title: string;
  page_name: string;
  author: string;
  account_id: string;
  account_status: "active" | "banned";
  body: string;
  created_at: string;
  reports: number;
  report_reasons: string[];
  hidden_at: string | null;
  hidden_reason: string | null;
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

/** A detail found automatically in a report's or a signal's text, with its words. */
export interface Detail {
  attribute: "occurrence" | "casualty_count" | "affected_count" | "magnitude" | "cause" | "status";
  value: boolean | number | string;
  unit?: string | null;
  surface: string;
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
  details: Detail[];
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
export type EvidenceRelation =
  "supports" | "partially_supports" | "contradicts" | "related" | "unrelated";

export interface EvidenceCounts {
  supports: number;
  partially_supports: number;
  contradicts: number;
  related: number;
  unrelated: number;
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
  occurred: boolean | null;
  ground_truth_sources: GroundTruthSource[];
  ground_truth_note: string | null;
}

export type GroundTruthKind = "official" | "news_followup" | "humanitarian_report" | "other";

export interface GroundTruthSource {
  reference: string;
  published_at: string;
  kind: GroundTruthKind;
}

export type ClaimAttribute =
  | "occurrence"
  | "event_type"
  | "location"
  | "start_time"
  | "end_time"
  | "status"
  | "magnitude"
  | "affected_count"
  | "casualty_count"
  | "cause";

/** Dataset labels on a link. */
export interface EvidenceLabels {
  conflicts: ClaimAttribute[];
  stale: boolean;
  confidence: 1 | 2 | 3;
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
  conflicts: ClaimAttribute[];
  stale: boolean;
  confidence: 1 | 2 | 3;
  judgement_count: number;
  agreement: "single" | "agree" | "disagree" | "resolved";
  gold_relation: EvidenceRelation | null;
  /** Exactly one of these is set. */
  field_report: FieldReport | null;
  signal: Signal | null;
  /** Set when this item repeats another source's: counted through that one. */
  copy_of: CopyInfo | null;
  /** How CARCUX reads the item against the event (read without the item itself). */
  stance?: StanceSuggestion | null;
}

/** CARCUX's suggested relation of an item to an event, with its reasons. A suggestion
 * only: the analyst decides. Never shown in the blind second-opinion queue. */
export interface StanceSuggestion {
  relation: EvidenceRelation;
  strength: "strong" | "medium" | "weak";
  reasons: string[];
  conflicts: ClaimAttribute[];
}

export interface CopyInfo {
  origin_evidence_id: string;
  origin_source: string;
  kind: "same_media" | "verbatim_copy" | "cites" | "rewrite" | "repost";
  text_similarity: number | null;
  reasons: string[];
  status: "detected" | "confirmed" | "rejected";
  decided_by: string | null;
}

export interface CandidateReport {
  report: FieldReport;
  distance_km: number;
  hours_apart: number;
  same_type: boolean;
  stance?: StanceSuggestion | null;
}

/** A suggested event. `method` says how the list was ranked: the 5 km / 48 h rule, or
 * the suggestion model once an admin has trained one. */
export interface CandidateEvent {
  event: CarcuxEvent;
  distance_km: number | null;
  hours_apart: number;
  same_type: boolean;
  same_family: boolean;
  method: "rule" | "model";
  score: number | null;
  text_similarity: number | null;
  hours_from_latest: number | null;
  model_id: string | null;
  stance?: StanceSuggestion | null;
}

/** Which suggestion an analyst linked from, recorded in the audit log. */
export interface SuggestionUsed {
  rank: number;
  method: "rule" | "model";
  score: number | null;
  model_id: string | null;
}

export interface SuggestionModel {
  id: string;
  created_at: string;
  created_by: { id: string; full_name: string } | null;
  active: boolean;
  items: number;
  events: number;
  positives: number;
  negatives: number;
  metrics: {
    held_out_items: number;
    held_out_events?: number;
    model_top1?: number;
    model_top3?: number;
    rule_top1?: number;
    rule_top3?: number;
    retrieved?: number;
  };
}

export interface SuggestionStatus {
  method: "rule" | "model";
  active: SuggestionModel | null;
  previous: SuggestionModel[];
  labelled_items: number;
  labelled_events: number;
  min_items: number;
  min_events: number;
  from_suggestions: { total: number; first: number; top3: number };
}

/** One source behind an assessment suggestion. */
export interface AssessmentReason {
  source: string;
  kind: string;
  vote: 1 | -1;
  reliability: number;
  learned: boolean;
  disputed: ClaimAttribute[];
}

/** The suggested assessment for an event: "start" (starting assumptions) or "model". */
export interface AssessmentSuggestion {
  label: Assessment;
  probability: number | null;
  method: "start" | "model";
  model_id: string | null;
  sources_supporting: number;
  sources_denying: number;
  credible_supporting: number;
  credible_denying: number;
  disputed: ClaimAttribute[];
  disputed_detected: ClaimAttribute[];
  reasons: AssessmentReason[];
  details: DetailSummary[];
  counted_once: number;
}

/** What an event's supporting sources state about one detail. */
export interface DetailSummary {
  attribute: "magnitude" | "affected_count" | "casualty_count" | "cause";
  estimate: number | string | boolean;
  unit: string | null;
  disputed: boolean;
  statements: {
    value: number | string | boolean;
    unit: string | null;
    source: string;
    reliability: number;
    surface: string;
  }[];
}

export interface AssessmentModel {
  id: string;
  created_at: string;
  created_by: { id: string; full_name: string } | null;
  active: boolean;
  events: number;
  happened: number;
  sources: number;
  metrics: {
    held_out_events: number;
    held_out_happened?: number;
    model_brier?: number;
    start_brier?: number;
    majority_brier?: number;
    model_accuracy?: number;
    start_accuracy?: number;
    majority_accuracy?: number;
  };
}

export interface AssessmentStatus {
  method: "start" | "model";
  active: AssessmentModel | null;
  resolved_events: number;
  resolved_happened: number;
  min_events: number;
  min_each: number;
  starting_rates: Record<string, number>;
  from_suggestions: { total: number; followed: number };
}

export function suggestionUsed(c: CandidateEvent, index: number): SuggestionUsed {
  return { rank: index + 1, method: c.method, score: c.score, model_id: c.model_id };
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
  second_opinions: number | null;
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
export type SourceType = "news" | "public_record" | "social" | "video_platform" | "other";

/** What a pasted link says about itself (CARCUX never opens it). */
export interface LinkPreview {
  platform: string;
  platform_label: string;
  kind: SourceType;
  url: string;
  post_id: string | null;
  account: string | null;
  video: boolean;
  existing_signal_id: string | null;
  known_source: string | null;
}
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
  window_start: string | null;
  window_end: string | null;
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
  details: Detail[];
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
  stance?: StanceSuggestion | null;
}

export interface District {
  name: string;
  division: string;
  latitude: number;
  longitude: number;
}

export interface DatasetProblem {
  kind: "needs_ground_truth" | "needs_conflicts" | "contradiction" | "outside_bangladesh";
  message: string;
  event_id: string | null;
  event_title: string | null;
  evidence_id: string | null;
}

export interface DatasetSummary {
  schema_version: string;
  guideline_version: string;
  counts: Record<string, number>;
  events_total: number;
  problems_by_kind: Record<string, number>;
  problems: DatasetProblem[];
}

export interface ImportRow {
  line: number;
  status: "add" | "duplicate" | "error";
  title: string;
  message: string;
  event_type: string | null;
  place: string | null;
  publisher: string | null;
  signal_id: string | null;
}

export interface ImportResult {
  dry_run: boolean;
  added: number;
  duplicates: number;
  errors: number;
  new_publishers: string[];
  rows: ImportRow[];
}

/** Second opinions, agreement and adjudication. */
export interface QueueItem {
  evidence_id: string;
  event: CarcuxEvent;
  field_report: FieldReport | null;
  signal: Signal | null;
  judgements: number;
}

export interface Judgement {
  id: string;
  annotator: { id: string; full_name: string };
  relation: EvidenceRelation;
  conflicts: ClaimAttribute[];
  stale: boolean;
  confidence: 1 | 2 | 3;
  note: string | null;
  blind: boolean;
  created_at: string;
  updated_at: string;
}

export interface Disagreement {
  evidence_id: string;
  event: CarcuxEvent;
  field_report: FieldReport | null;
  signal: Signal | null;
  working: EvidenceRelation;
  judgements: Judgement[];
  gold_relation: EvidenceRelation | null;
  gold_by: { id: string; full_name: string } | null;
  gold_at: string | null;
}

export interface AgreementStats {
  items_with_two: number;
  items_total: number;
  percent: number | null;
  kappa: number | null;
  alpha: number | null;
  target: number;
  matrix: Record<string, Record<string, number>>;
  by_label: Record<string, number>;
  open_disagreements: number;
}
