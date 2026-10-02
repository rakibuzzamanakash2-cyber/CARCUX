"use server";

import { redirect } from "next/navigation";

import { api, apiFetch, ApiError } from "@/lib/api";
import { requireRole } from "@/lib/dal";
import { isUuid } from "@/lib/format";
import {
  REPORT_REVIEWERS,
  REPORT_SUBMITTERS,
  type ActionState,
  type FieldReport,
  type VerifyResult,
} from "@/lib/types";

const TEXT_FIELDS = [
  "client_report_id",
  "text",
  "latitude",
  "longitude",
  "observed_at",
  "event_type",
  "place_name",
  "location_accuracy_m",
] as const;

export async function submitReport(_prev: ActionState, formData: FormData): Promise<ActionState> {
  // Server Actions are public endpoints: always re-check authorization here.
  await requireRole(...REPORT_SUBMITTERS);

  // Forward only the fields the backend expects; the backend validates them all.
  const body = new FormData();
  for (const key of TEXT_FIELDS) {
    const value = formData.get(key);
    if (typeof value === "string" && value.trim() !== "") body.set(key, value);
  }
  for (const photo of formData.getAll("photos")) {
    if (photo instanceof File && photo.size > 0) body.append("photos", photo, photo.name);
  }

  let report: FieldReport;
  let created: boolean;
  try {
    const response = await apiFetch("/field-reports", { method: "POST", body });
    created = response.status === 201;
    report = (await response.json()) as FieldReport;
  } catch (error) {
    if (error instanceof ApiError && error.status === 409) {
      return {
        ok: false,
        message:
          "This form was already used for a different report. Reload the page to start a new one.",
      };
    }
    return {
      ok: false,
      message:
        error instanceof ApiError
          ? error.detail
          : "The report could not be sent. Nothing was lost: try again.",
    };
  }
  // Outside try: redirect() works by throwing.
  redirect(`/field-reports/${report.id}?submitted=${created ? "new" : "again"}`);
}

export async function verifyReport(
  reportId: string,
): Promise<{ ok: true; result: VerifyResult } | { ok: false; message: string }> {
  await requireRole(...REPORT_REVIEWERS);
  if (!isUuid(reportId)) return { ok: false, message: "Unknown report." };
  try {
    const result = await api<VerifyResult>(`/field-reports/${reportId}/verify`);
    return { ok: true, result };
  } catch (error) {
    return {
      ok: false,
      message: error instanceof ApiError ? error.detail : "The check could not be run.",
    };
  }
}
