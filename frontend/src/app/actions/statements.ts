"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { api, ApiError } from "@/lib/api";
import { requireRole } from "@/lib/dal";
import { isUuid } from "@/lib/format";
import { FINDINGS, type ActionState, type StatementDetail } from "@/lib/types";

const VALID = new Set<string>(FINDINGS.map((f) => f.value));

export async function publishStatement(
  eventId: string,
  _prev: ActionState,
  formData: FormData,
): Promise<ActionState> {
  await requireRole("official");
  const finding = String(formData.get("finding") ?? "");
  const title = String(formData.get("title") ?? "").trim();
  const body = String(formData.get("body") ?? "").trim();
  const supersedes = String(formData.get("supersedes_id") ?? "");
  if (!isUuid(eventId)) return { ok: false, message: "Unknown event." };
  if (!VALID.has(finding)) return { ok: false, message: "Choose your finding." };
  if (title.length < 5) return { ok: false, message: "Give the statement a title." };
  if (body.length < 20)
    return { ok: false, message: "Write the statement (20 characters or more)." };
  let statement: StatementDetail;
  try {
    statement = await api<StatementDetail>("/statements", {
      method: "POST",
      body: JSON.stringify({
        event_id: eventId,
        finding,
        title,
        body,
        supersedes_id: isUuid(supersedes) ? supersedes : null,
      }),
    });
  } catch (error) {
    return {
      ok: false,
      message: error instanceof ApiError ? error.detail : "Could not publish the statement.",
    };
  }
  revalidatePath(`/events/${eventId}`);
  revalidatePath("/statements");
  revalidatePath(`/official-pages/${statement.page.slug}`);
  redirect(`/statements/${statement.id}?published=1`);
}
