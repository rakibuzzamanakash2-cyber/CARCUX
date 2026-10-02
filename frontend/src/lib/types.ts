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
}

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
