"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { api, ApiError } from "@/lib/api";
import { requireRole } from "@/lib/dal";
import { CLAIM_ATTRIBUTES, RELATIONS } from "@/lib/events";
import { DHAKA_OFFSET, isUuid } from "@/lib/format";
import {
  REPORT_REVIEWERS,
  type ActionState,
  type EvidenceRelation,
  type IngestRun,
  type Signal,
  type SignalStatus,
} from "@/lib/types";

const RELATION_VALUES = new Set<string>(RELATIONS.map((r) => r.value));
const CLAIMS = new Set<string>(CLAIM_ATTRIBUTES.map((a) => a.value));
const STATUSES = new Set<SignalStatus>(["new", "reviewed", "dismissed"]);
const LOCAL_DATETIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/;

function failure(error: unknown, fallback: string): ActionState {
  return {
    ok: false,
    message: error instanceof ApiError ? error.detail : fallback,
  };
}

function text(formData: FormData, key: string): string {
  return String(formData.get(key) ?? "").trim();
}

function refresh(signalId?: string, eventId?: string) {
  revalidatePath("/signals");
  if (signalId) revalidatePath(`/signals/${signalId}`);
  if (eventId) revalidatePath(`/events/${eventId}`);
  revalidatePath("/", "layout"); // status bar, sidebar counts, map
}

/** Link a signal to an event as evidence. */
export async function linkSignal(
  eventId: string,
  signalId: string,
  relation: EvidenceRelation,
  conflicts: string[] = [],
): Promise<ActionState> {
  await requireRole(...REPORT_REVIEWERS);
  if (!isUuid(eventId) || !isUuid(signalId) || !RELATION_VALUES.has(relation)) {
    return { ok: false, message: "Unknown event, signal or relation." };
  }
  try {
    await api(`/events/${eventId}/evidence`, {
      method: "POST",
      body: JSON.stringify({
        signal_id: signalId,
        relation,
        conflicts: conflicts.filter((c) => CLAIMS.has(c)),
      }),
    });
  } catch (error) {
    return failure(error, "Could not link the signal.");
  }
  refresh(signalId, eventId);
  return { ok: true, message: "Linked." };
}

/** Triage a signal: reviewed, dismissed (with a reason) or back to new. */
export async function reviewSignal(
  signalId: string,
  status: SignalStatus,
  note?: string,
): Promise<ActionState> {
  await requireRole(...REPORT_REVIEWERS);
  if (!isUuid(signalId) || !STATUSES.has(status)) return { ok: false, message: "Unknown signal." };
  try {
    await api(`/signals/${signalId}/review`, {
      method: "POST",
      body: JSON.stringify({ status, note: note?.trim() || null }),
    });
  } catch (error) {
    return failure(error, "Could not save the decision.");
  }
  refresh(signalId);
  const done = {
    reviewed: "Marked reviewed.",
    dismissed: "Dismissed.",
    new: "Marked as new.",
  };
  return { ok: true, message: done[status] };
}

/** Enter a bulletin by hand (BMD, FFWC). */
export async function enterBulletin(_prev: ActionState, formData: FormData): Promise<ActionState> {
  await requireRole(...REPORT_REVIEWERS);
  const published = text(formData, "published_at");
  const until = text(formData, "valid_until");
  if (!LOCAL_DATETIME.test(published)) return { ok: false, message: "Enter when it was issued." };
  if (until && !LOCAL_DATETIME.test(until))
    return {
      ok: false,
      message: "Enter a valid 'valid until' time, or leave it empty.",
    };
  const body = {
    source_id: text(formData, "source_id"),
    title: text(formData, "title"),
    text: text(formData, "text") || null,
    url: text(formData, "url") || null,
    event_type: text(formData, "event_type"),
    severity: text(formData, "severity") || null,
    published_at: `${published}:00${DHAKA_OFFSET}`,
    valid_until: until ? `${until}:00${DHAKA_OFFSET}` : null,
    district: text(formData, "district") || null,
    place_name: text(formData, "place_name") || null,
    language: text(formData, "language") || "en",
  };
  if (!isUuid(body.source_id)) return { ok: false, message: "Choose who issued it." };
  if (!body.event_type) return { ok: false, message: "Choose what it is about." };
  if (!body.district) return { ok: false, message: "Choose the district it concerns most." };

  let signal: Signal;
  try {
    signal = await api<Signal>("/signals", {
      method: "POST",
      body: JSON.stringify(body),
    });
  } catch (error) {
    return failure(error, "Could not save the bulletin.");
  }
  refresh(signal.id);
  redirect(`/signals/${signal.id}?entered=1`);
}

/** Admin: add a news feed. */
export async function addFeed(_prev: ActionState, formData: FormData): Promise<ActionState> {
  await requireRole("admin");
  const body = {
    name: text(formData, "name"),
    url: text(formData, "url"),
    language: text(formData, "language") || "en",
    interval_minutes: Number(text(formData, "interval_minutes") || 30),
  };
  try {
    await api("/sources", { method: "POST", body: JSON.stringify(body) });
  } catch (error) {
    return failure(error, "Could not add the feed.");
  }
  revalidatePath("/sources");
  return {
    ok: true,
    message: `Added ${body.name}. It will be read within a minute.`,
  };
}

/** Admin: switch a source on or off. */
export async function setSourceEnabled(sourceId: string, enabled: boolean): Promise<ActionState> {
  await requireRole("admin");
  if (!isUuid(sourceId)) return { ok: false, message: "Unknown source." };
  try {
    await api(`/sources/${sourceId}`, {
      method: "PATCH",
      body: JSON.stringify({ enabled }),
    });
  } catch (error) {
    return failure(error, "Could not change the source.");
  }
  revalidatePath("/sources");
  return { ok: true, message: enabled ? "Switched on." : "Switched off." };
}

/** Admin: read a source now and say what came back. */
export async function fetchNow(sourceId: string): Promise<ActionState> {
  await requireRole("admin");
  if (!isUuid(sourceId)) return { ok: false, message: "Unknown source." };
  let run: IngestRun;
  try {
    run = await api<IngestRun>(`/sources/${sourceId}/fetch`, {
      method: "POST",
    });
  } catch (error) {
    return failure(error, "Could not read the source.");
  }
  revalidatePath("/sources");
  revalidatePath("/signals");
  revalidatePath("/", "layout");
  if (!run.ok) return { ok: false, message: run.error ?? "The source could not be read." };
  return {
    ok: true,
    message: `Read ${run.fetched} items: ${run.created} new, ${run.updated} updated, ${run.skipped} not relevant.`,
  };
}
