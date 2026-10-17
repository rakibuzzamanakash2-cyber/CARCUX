"use server";

import { revalidatePath } from "next/cache";

import { api, ApiError } from "@/lib/api";
import { requireRole } from "@/lib/dal";
import { isUuid } from "@/lib/format";
import { REPORT_REVIEWERS, type ActionState, type EvidenceRequest } from "@/lib/types";

function refresh(eventId: string) {
  revalidatePath(`/events/${eventId}`);
  revalidatePath("/review/events");
  revalidatePath("/field-reports");
}

function failure(error: unknown, fallback: string): ActionState {
  return { ok: false, message: error instanceof ApiError ? error.detail : fallback };
}

/** Ask field workers to go and check the event. */
export async function requestEvidence(
  eventId: string,
  _prev: ActionState,
  formData: FormData,
): Promise<ActionState> {
  // Server Actions are public endpoints: always re-check authorization here.
  await requireRole(...REPORT_REVIEWERS);
  if (!isUuid(eventId)) return { ok: false, message: "Unknown event." };
  const question = String(formData.get("question") ?? "").trim();
  if (question.length < 10) return { ok: false, message: "Write the question in a sentence." };
  if (question.length > 500) return { ok: false, message: "Keep it under 500 characters." };
  try {
    await api<EvidenceRequest>(`/events/${eventId}/evidence-requests`, {
      method: "POST",
      body: JSON.stringify({ question }),
    });
  } catch (error) {
    return failure(error, "Could not send the request.");
  }
  refresh(eventId);
  return { ok: true, message: "Sent. Field workers will see it in their list of checks." };
}

export async function closeRequest(
  eventId: string,
  requestId: string,
  status: "answered" | "cancelled",
): Promise<ActionState> {
  await requireRole(...REPORT_REVIEWERS);
  if (!isUuid(eventId) || !isUuid(requestId)) return { ok: false, message: "Unknown request." };
  if (status !== "answered" && status !== "cancelled")
    return { ok: false, message: "Unknown status." };
  try {
    await api<EvidenceRequest>(`/evidence-requests/${requestId}/close`, {
      method: "POST",
      body: JSON.stringify({ status }),
    });
  } catch (error) {
    return failure(error, "Could not close the request.");
  }
  refresh(eventId);
  return { ok: true, message: status === "answered" ? "Closed as answered." : "Cancelled." };
}
