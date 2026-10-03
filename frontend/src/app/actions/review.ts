"use server";

import { revalidatePath } from "next/cache";

import { api, apiFetch, ApiError } from "@/lib/api";
import { requireRole, verifySession } from "@/lib/dal";
import { isUuid } from "@/lib/format";
import { setToken } from "@/lib/session";
import { REPORT_REVIEWERS, type ActionState, type ReportStatus } from "@/lib/types";

const STATUSES = new Set<ReportStatus>(["submitted", "reviewed", "dismissed"]);

function failure(error: unknown, fallback: string): ActionState {
  return { ok: false, message: error instanceof ApiError ? error.detail : fallback };
}

/** Triage a field report: reviewed, dismissed (with a reason) or back to new. */
export async function reviewReport(
  reportId: string,
  status: ReportStatus,
  note?: string,
): Promise<ActionState> {
  await requireRole(...REPORT_REVIEWERS);
  if (!isUuid(reportId) || !STATUSES.has(status)) return { ok: false, message: "Unknown report." };
  try {
    await api(`/field-reports/${reportId}/review`, {
      method: "POST",
      body: JSON.stringify({ status, note: note?.trim() || null }),
    });
  } catch (error) {
    return failure(error, "Could not save the decision.");
  }
  revalidatePath("/review");
  revalidatePath("/field-reports");
  revalidatePath(`/field-reports/${reportId}`);
  revalidatePath("/", "layout");
  const done = {
    reviewed: "Marked reviewed.",
    dismissed: "Dismissed.",
    submitted: "Back in the queue.",
  };
  return { ok: true, message: done[status] };
}

/** Change your own password. The backend signs out other sessions and returns a new token. */
export async function changePassword(_prev: ActionState, formData: FormData): Promise<ActionState> {
  await verifySession();
  const current = String(formData.get("current_password") ?? "");
  const next = String(formData.get("new_password") ?? "");
  const confirm = String(formData.get("confirm_password") ?? "");
  if (next !== confirm) return { ok: false, message: "The two new passwords do not match." };
  if (next.length < 12) return { ok: false, message: "Use at least 12 characters." };
  try {
    const token = await api<{ access_token: string; expires_in: number }>("/auth/password", {
      method: "POST",
      body: JSON.stringify({ current_password: current, new_password: next }),
    });
    await setToken(token.access_token, token.expires_in);
  } catch (error) {
    return failure(error, "Could not change the password.");
  }
  return { ok: true, message: "Password changed. Your other sessions have been signed out." };
}

/** Admin: set a temporary password for someone who forgot theirs. */
export async function resetPassword(userId: string, password: string): Promise<ActionState> {
  await requireRole("admin");
  if (!isUuid(userId)) return { ok: false, message: "Unknown account." };
  if (password.length < 12) return { ok: false, message: "Use at least 12 characters." };
  try {
    await apiFetch(`/users/${userId}/password`, {
      method: "POST",
      body: JSON.stringify({ new_password: password }),
    });
  } catch (error) {
    return failure(error, "Could not reset the password.");
  }
  revalidatePath("/users");
  return { ok: true, message: "Temporary password set. Share it privately; they are signed out." };
}
