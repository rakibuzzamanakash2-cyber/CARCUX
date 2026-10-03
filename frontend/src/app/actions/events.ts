"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { api, apiFetch, ApiError } from "@/lib/api";
import { requireRole } from "@/lib/dal";
import { ASSESSMENTS, PRIORITIES, RELATIONS, STATUSES } from "@/lib/events";
import { DHAKA_OFFSET, isUuid } from "@/lib/format";
import {
  REPORT_REVIEWERS,
  type ActionState,
  type Assessment,
  type CarcuxEvent,
  type EventStatus,
  type EvidenceRelation,
  type Priority,
} from "@/lib/types";

const RELATION_VALUES = new Set<string>(RELATIONS.map((r) => r.value));
const STATUS_VALUES = new Set<string>(STATUSES.map((s) => s.value));
const PRIORITY_VALUES = new Set<string>(PRIORITIES.map((p) => p.value));
const ASSESSMENT_VALUES = new Set<string>(ASSESSMENTS.map((a) => a.value));
const LOCAL_DATETIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/;

function failure(error: unknown, fallback: string): ActionState {
  return { ok: false, message: error instanceof ApiError ? error.detail : fallback };
}

function text(formData: FormData, key: string): string {
  return String(formData.get(key) ?? "").trim();
}

/** A datetime-local value, read as Dhaka time. */
function dhakaTime(value: string): string | null {
  return LOCAL_DATETIME.test(value) ? `${value}:00${DHAKA_OFFSET}` : null;
}

function refresh(eventId: string, reportIds: string[] = []) {
  revalidatePath("/events");
  revalidatePath(`/events/${eventId}`);
  revalidatePath("/", "layout"); // status bar and sidebar counts
  revalidatePath("/review");
  for (const id of reportIds) revalidatePath(`/field-reports/${id}`);
}

export async function createEvent(_prev: ActionState, formData: FormData): Promise<ActionState> {
  // Server Actions are public endpoints: always re-check authorization here.
  await requireRole(...REPORT_REVIEWERS);

  const startedAt = dhakaTime(text(formData, "started_at"));
  if (!startedAt) return { ok: false, message: "Enter when it started." };
  const reportIds = formData
    .getAll("field_report_ids")
    .map(String)
    .filter((id) => isUuid(id));
  const signalIds = formData
    .getAll("signal_ids")
    .map(String)
    .filter((id) => isUuid(id));
  const priority = text(formData, "priority");
  const body = {
    title: text(formData, "title"),
    event_type: text(formData, "event_type"),
    summary: text(formData, "summary") || null,
    place_name: text(formData, "place_name") || null,
    latitude: Number(text(formData, "latitude")),
    longitude: Number(text(formData, "longitude")),
    started_at: startedAt,
    priority: PRIORITY_VALUES.has(priority) ? priority : "medium",
    field_report_ids: reportIds,
    signal_ids: signalIds,
  };
  if (!body.event_type) return { ok: false, message: "Choose the type of event." };
  if (Number.isNaN(body.latitude) || Number.isNaN(body.longitude) || !text(formData, "latitude")) {
    return { ok: false, message: "Enter the location as latitude and longitude." };
  }

  let event: CarcuxEvent;
  try {
    event = await api<CarcuxEvent>("/events", { method: "POST", body: JSON.stringify(body) });
  } catch (error) {
    return failure(error, "Could not create the event.");
  }
  refresh(event.id, reportIds);
  for (const id of signalIds) revalidatePath(`/signals/${id}`);
  redirect(`/events/${event.id}?created=1`);
}

export interface EventChanges {
  title?: string;
  summary?: string | null;
  place_name?: string | null;
  status?: EventStatus;
  priority?: Priority;
  assessment?: Assessment;
}

export async function updateEvent(eventId: string, changes: EventChanges): Promise<ActionState> {
  await requireRole(...REPORT_REVIEWERS);
  if (!isUuid(eventId)) return { ok: false, message: "Unknown event." };
  if (changes.status && !STATUS_VALUES.has(changes.status))
    return { ok: false, message: "Unknown status." };
  if (changes.priority && !PRIORITY_VALUES.has(changes.priority))
    return { ok: false, message: "Unknown priority." };
  if (changes.assessment && !ASSESSMENT_VALUES.has(changes.assessment))
    return { ok: false, message: "Unknown assessment." };

  const body: Record<string, unknown> = { ...changes };
  try {
    // Closing an event records when; reopening it clears the end time.
    if (changes.status) {
      const current = await api<CarcuxEvent>(`/events/${eventId}`);
      const closing = changes.status === "resolved" || changes.status === "dismissed";
      if (closing && !current.ended_at) body.ended_at = new Date().toISOString();
      if (!closing && current.ended_at) body.ended_at = null;
    }
    await api<CarcuxEvent>(`/events/${eventId}`, { method: "PATCH", body: JSON.stringify(body) });
  } catch (error) {
    return failure(error, "Could not save the change.");
  }
  refresh(eventId);
  return { ok: true, message: "Saved." };
}

export async function linkReport(
  eventId: string,
  reportId: string,
  relation: EvidenceRelation,
): Promise<ActionState> {
  await requireRole(...REPORT_REVIEWERS);
  if (!isUuid(eventId) || !isUuid(reportId) || !RELATION_VALUES.has(relation)) {
    return { ok: false, message: "Unknown event, report or relation." };
  }
  try {
    await api(`/events/${eventId}/evidence`, {
      method: "POST",
      body: JSON.stringify({ field_report_id: reportId, relation }),
    });
  } catch (error) {
    return failure(error, "Could not link the report.");
  }
  refresh(eventId, [reportId]);
  return { ok: true, message: "Linked." };
}

export async function changeRelation(
  eventId: string,
  evidenceId: string,
  reportId: string,
  relation: EvidenceRelation,
): Promise<ActionState> {
  await requireRole(...REPORT_REVIEWERS);
  if (!isUuid(eventId) || !isUuid(evidenceId) || !RELATION_VALUES.has(relation)) {
    return { ok: false, message: "Unknown evidence or relation." };
  }
  try {
    await api(`/events/${eventId}/evidence/${evidenceId}`, {
      method: "PATCH",
      body: JSON.stringify({ relation }),
    });
  } catch (error) {
    return failure(error, "Could not change the relation.");
  }
  refresh(eventId, isUuid(reportId) ? [reportId] : []);
  return { ok: true, message: "Saved." };
}

export async function unlinkEvidence(
  eventId: string,
  evidenceId: string,
  reportId: string,
): Promise<ActionState> {
  await requireRole(...REPORT_REVIEWERS);
  if (!isUuid(eventId) || !isUuid(evidenceId)) return { ok: false, message: "Unknown evidence." };
  try {
    await apiFetch(`/events/${eventId}/evidence/${evidenceId}`, { method: "DELETE" });
  } catch (error) {
    return failure(error, "Could not unlink the report.");
  }
  refresh(eventId, isUuid(reportId) ? [reportId] : []);
  return { ok: true, message: "Unlinked." };
}
