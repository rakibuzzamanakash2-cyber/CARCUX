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
