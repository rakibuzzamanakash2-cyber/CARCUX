"use server";

import { revalidatePath } from "next/cache";

import { api, apiFetch, ApiError } from "@/lib/api";
import type { ActionState, TwoFactorSetup } from "@/lib/types";

export type SetupState =
  { ok: boolean; message: string; setup?: TwoFactorSetup; codes?: string[] } | undefined;

function failed(error: unknown, fallback: string): { ok: false; message: string } {
  return { ok: false, message: error instanceof ApiError ? error.detail : fallback };
}

/** Step 1: a new secret and QR code to add to an authenticator app. */
export async function startTwoFactor(): Promise<SetupState> {
  try {
    const setup = await api<TwoFactorSetup>("/auth/two-factor/setup", { method: "POST" });
    return { ok: true, message: "", setup };
  } catch (error) {
    return failed(error, "Could not start the set-up. Try again.");
  }
}

/** Step 2: confirm with a code from the app; returns the recovery codes, shown once. */
export async function enableTwoFactor(_prev: SetupState, formData: FormData): Promise<SetupState> {
  const code = String(formData.get("code") ?? "").trim();
  if (!code) return { ok: false, message: "Enter the 6-digit code from the app." };
  try {
    const out = await api<{ recovery_codes: string[] }>("/auth/two-factor/enable", {
      method: "POST",
      body: JSON.stringify({ code }),
    });
    // No revalidation here: refreshing would replace the set-up panel before the
    // recovery codes are seen. The panel refreshes when they are saved.
    return { ok: true, message: "Two-factor sign-in is on.", codes: out.recovery_codes };
  } catch (error) {
    return failed(error, "Could not turn it on. Try again.");
  }
}

export async function newRecoveryCodes(_prev: SetupState, formData: FormData): Promise<SetupState> {
  const code = String(formData.get("code") ?? "").trim();
  try {
    const out = await api<{ recovery_codes: string[] }>("/auth/two-factor/recovery-codes", {
      method: "POST",
      body: JSON.stringify({ code }),
    });
    revalidatePath("/account");
    return {
      ok: true,
      message: "New recovery codes. The old ones no longer work.",
      codes: out.recovery_codes,
    };
  } catch (error) {
    return failed(error, "Could not make new codes. Try again.");
  }
}

export async function disableTwoFactor(
  _prev: ActionState,
  formData: FormData,
): Promise<ActionState> {
  const password = String(formData.get("password") ?? "");
  const code = String(formData.get("code") ?? "").trim();
  if (!password || !code) return { ok: false, message: "Enter your password and a code." };
  try {
    await apiFetch("/auth/two-factor/disable", {
      method: "POST",
      body: JSON.stringify({ password, code }),
    });
    revalidatePath("/account");
    return { ok: true, message: "Two-factor sign-in is off." };
  } catch (error) {
    return failed(error, "Could not turn it off. Try again.");
  }
}

/** Admins: turn off someone's two-factor sign-in after a lost phone. */
export async function resetTwoFactor(userId: string): Promise<ActionState> {
  try {
    await apiFetch(`/users/${userId}/two-factor/reset`, { method: "POST" });
    revalidatePath("/users");
    return {
      ok: true,
      message: "Two-factor reset. They are signed out and can sign in with their password.",
    };
  } catch (error) {
    return failed(error, "Could not reset it. Try again.");
  }
}
