"use server";

import { redirect } from "next/navigation";

import { api, ApiError } from "@/lib/api";
import { clearToken, setToken } from "@/lib/session";

interface LoginResult {
  access_token: string | null;
  expires_in: number;
  two_factor_required: boolean;
  challenge: string | null;
}

/** The sign-in form's state: a message, and the challenge while a code is asked for. */
export type LoginState = { ok: boolean; message: string; challenge?: string } | undefined;

/** Only allow redirects to paths on this site ("/users"), never "//evil.com" or URLs. */
function safeNext(value: FormDataEntryValue | null): string {
  const next = typeof value === "string" ? value : "";
  return next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/\\") ? next : "/";
}

export async function login(_prev: LoginState, formData: FormData): Promise<LoginState> {
  const challenge = String(formData.get("challenge") ?? "");
  if (challenge) return secondStep(challenge, formData);
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  if (!email || !password) return { ok: false, message: "Enter your email and password." };

  try {
    const result = await api<LoginResult>("/auth/login", {
      method: "POST",
      auth: false,
      body: JSON.stringify({ email, password }),
    });
    if (result.two_factor_required && result.challenge) {
      return { ok: true, message: "", challenge: result.challenge };
    }
    await setToken(result.access_token ?? "", result.expires_in);
  } catch (error) {
    if (error instanceof ApiError && (error.status === 401 || error.status === 422)) {
      return { ok: false, message: "Invalid email or password." };
    }
    return {
      ok: false,
      message: error instanceof ApiError ? error.detail : "Login failed. Try again.",
    };
  }
  // redirect() works by throwing, so it must stay outside the try block.
  redirect(safeNext(formData.get("next")));
}

/** The code from the authenticator app (or a recovery code), after the password. */
async function secondStep(challenge: string, formData: FormData): Promise<LoginState> {
  const code = String(formData.get("code") ?? "").trim();
  if (!code) return { ok: false, message: "Enter the code from your app.", challenge };
  try {
    const result = await api<LoginResult>("/auth/login/two-factor", {
      method: "POST",
      auth: false,
      body: JSON.stringify({ challenge, code }),
    });
    await setToken(result.access_token ?? "", result.expires_in);
  } catch (error) {
    const message = error instanceof ApiError ? error.detail : "Sign-in failed. Try again.";
    // An expired or refused challenge means starting again with the password.
    const again =
      error instanceof ApiError && error.status === 401 && /expired|^Sign in again/.test(message);
    return { ok: false, message, challenge: again ? undefined : challenge };
  }
  redirect(safeNext(formData.get("next")));
}

export async function logout(): Promise<void> {
  await clearToken();
  redirect("/login");
}
