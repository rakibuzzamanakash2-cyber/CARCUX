"use server";

import { revalidatePath } from "next/cache";

import { api, apiFetch, ApiError } from "@/lib/api";
import { requireRole } from "@/lib/dal";
import type { ActionState, AssessmentModel } from "@/lib/types";

function failure(error: unknown, fallback: string): ActionState {
  return { ok: false, message: error instanceof ApiError ? error.detail : fallback };
}

/** Learn source reliabilities from events with ground truth (admins only). */
export async function trainAssessment(): Promise<ActionState> {
  await requireRole("admin");
  let model: AssessmentModel;
  try {
    model = await api<AssessmentModel>("/assessment/model/train", { method: "POST" });
  } catch (error) {
    return failure(error, "Could not train the model.");
  }
  revalidatePath("/", "layout");
  const m = model.metrics;
  return {
    ok: true,
    message:
      m.model_brier === undefined
        ? `Trained on ${model.events} events and switched on. Too few held-out events to measure it yet.`
        : `Trained on ${model.events} events and switched on. Held-out Brier score ${m.model_brier.toFixed(3)} (starting assumptions ${m.start_brier?.toFixed(3)}, majority vote ${m.majority_brier?.toFixed(3)}; lower is better).`,
  };
}

/** Go back to the starting assumptions (admins only). */
export async function deactivateAssessment(): Promise<ActionState> {
  await requireRole("admin");
  try {
    await apiFetch("/assessment/model/deactivate", { method: "POST" });
  } catch (error) {
    return failure(error, "Could not switch the model off.");
  }
  revalidatePath("/", "layout");
  return { ok: true, message: "Assessment suggestions use the starting assumptions again." };
}
