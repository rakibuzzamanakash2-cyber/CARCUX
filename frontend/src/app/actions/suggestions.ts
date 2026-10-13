"use server";

import { revalidatePath } from "next/cache";

import { api, apiFetch, ApiError } from "@/lib/api";
import { requireRole } from "@/lib/dal";
import type { ActionState, SuggestionModel } from "@/lib/types";

function failure(error: unknown, fallback: string): ActionState {
  return { ok: false, message: error instanceof ApiError ? error.detail : fallback };
}

function pct(x?: number): string {
  return x === undefined ? "–" : `${Math.round(x * 100)}%`;
}

/** Train the event suggestion model on the links analysts have made (admins only). */
export async function trainSuggestions(): Promise<ActionState> {
  await requireRole("admin");
  let model: SuggestionModel;
  try {
    model = await api<SuggestionModel>("/suggestions/model/train", { method: "POST" });
  } catch (error) {
    return failure(error, "Could not train the model.");
  }
  revalidatePath("/", "layout");
  const m = model.metrics;
  return {
    ok: true,
    message:
      m.model_top1 === undefined
        ? `Trained on ${model.items} links and switched on. Too few held-out events to measure it yet.`
        : `Trained on ${model.items} links and switched on. First suggestion right: ${pct(m.model_top1)} (rule ${pct(m.rule_top1)}).`,
  };
}

/** Go back to the 5 km / 48 h rule (admins only). */
export async function deactivateSuggestions(): Promise<ActionState> {
  await requireRole("admin");
  try {
    await apiFetch("/suggestions/model/deactivate", { method: "POST" });
  } catch (error) {
    return failure(error, "Could not switch the model off.");
  }
  revalidatePath("/", "layout");
  return { ok: true, message: "Suggestions use the 5 km / 48 h rule again." };
}
