"use server";

import { redirect } from "next/navigation";

import { api, ApiError } from "@/lib/api";
import { clearToken, setToken } from "@/lib/session";
import type { ActionState } from "@/lib/types";

interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

/** Only allow redirects to paths on this site ("/users"), never "//evil.com" or URLs. */
function safeNext(value: FormDataEntryValue | null): string {
  const next = typeof value === "string" ? value : "";
  return next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/\\") ? next : "/";
}

export async function login(_prev: ActionState, formData: FormData): Promise<ActionState> {
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  if (!email || !password) return { ok: false, message: "Enter your email and password." };

  try {
    const token = await api<TokenResponse>("/auth/login", {
      method: "POST",
      auth: false,
      body: JSON.stringify({ email, password }),
    });
    await setToken(token.access_token, token.expires_in);
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

export async function logout(): Promise<void> {
  await clearToken();
  redirect("/login");
}
