import "server-only";

import { cookies } from "next/headers";
import { cache } from "react";

import { apiFetch, ApiError } from "@/lib/api";
import type { PublicMe } from "@/lib/types";

/**
 * The public site's session: a separate cookie and a separate kind of token from
 * staff sign-in. Staff pages never read it, and the backend refuses it on staff
 * endpoints.
 */
export const PUBLIC_COOKIE = "carcux_public";

export async function getPublicToken(): Promise<string | undefined> {
  return (await cookies()).get(PUBLIC_COOKIE)?.value;
}

export async function setPublicToken(token: string, maxAgeSeconds: number): Promise<void> {
  (await cookies()).set(PUBLIC_COOKIE, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/public",
    maxAge: maxAgeSeconds,
  });
}

export async function clearPublicToken(): Promise<void> {
  (await cookies()).delete({ name: PUBLIC_COOKIE, path: "/public" });
}

/** Call the backend's public API, as the signed-in person when there is one. */
export async function publicApi<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await getPublicToken();
  const call = (withToken: boolean) =>
    apiFetch(`/public${path}`, {
      ...init,
      auth: false,
      headers: withToken && token ? { Authorization: `Bearer ${token}` } : {},
    });
  let response: Response;
  try {
    response = await call(true);
  } catch (error) {
    // A session that ended (signed out elsewhere, banned, deleted) still reads as anyone.
    const reading = !init.method || init.method === "GET";
    if (!(token && reading && error instanceof ApiError && error.status === 401)) throw error;
    response = await call(false);
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

/** The signed-in person, or null (also when their session ended). */
export const publicMe = cache(async (): Promise<PublicMe | null> => {
  if (!(await getPublicToken())) return null;
  try {
    return await publicApi<PublicMe>("/auth/me");
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
});
