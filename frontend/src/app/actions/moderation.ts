"use server";

import { api, apiFetch, ApiError } from "@/lib/api";
import { requireRole } from "@/lib/dal";
import { isUuid } from "@/lib/format";
import type { ActionState } from "@/lib/types";

function failure(error: unknown, fallback: string): ActionState {
  return { ok: false, message: error instanceof ApiError ? error.detail : fallback };
}

// Nothing is revalidated: the public pages are rendered on every request, and on the
// moderation list each decided item stays in view, marked done, until the next load
// (revalidating would refresh the list and take the item and its confirmation away).
function refresh() {}

export async function hideComment(commentId: string, reason: string): Promise<ActionState> {
  await requireRole("admin", "official");
  if (!isUuid(commentId)) return { ok: false, message: "Unknown comment." };
  if (reason.trim().length < 3) return { ok: false, message: "Give a reason." };
  try {
    await api(`/moderation/comments/${commentId}/hide`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    });
  } catch (error) {
    return failure(error, "Could not hide it.");
  }
  refresh();
  return { ok: true, message: "Hidden." };
}

export async function keepComment(commentId: string): Promise<ActionState> {
  await requireRole("admin", "official");
  if (!isUuid(commentId)) return { ok: false, message: "Unknown comment." };
  try {
    await api(`/moderation/comments/${commentId}/restore`, { method: "POST" });
  } catch (error) {
    return failure(error, "Could not restore it.");
  }
  refresh();
  return { ok: true, message: "Kept up." };
}

export async function banAccount(accountId: string, reason: string): Promise<ActionState> {
  await requireRole("admin");
  if (!isUuid(accountId)) return { ok: false, message: "Unknown account." };
  if (reason.trim().length < 3) return { ok: false, message: "Give a reason." };
  try {
    await apiFetch(`/moderation/accounts/${accountId}/ban`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    });
  } catch (error) {
    return failure(error, "Could not ban the account.");
  }
  refresh();
  return { ok: true, message: "Banned; their comments are hidden." };
}

export async function unbanAccount(accountId: string): Promise<ActionState> {
  await requireRole("admin");
  if (!isUuid(accountId)) return { ok: false, message: "Unknown account." };
  try {
    await apiFetch(`/moderation/accounts/${accountId}/unban`, { method: "POST" });
  } catch (error) {
    return failure(error, "Could not lift the ban.");
  }
  refresh();
  return { ok: true, message: "Ban lifted. Their hidden comments stay hidden." };
}
