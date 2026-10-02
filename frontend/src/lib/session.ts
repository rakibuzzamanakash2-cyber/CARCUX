import "server-only";

import { cookies } from "next/headers";

/**
 * The backend access token lives only in an httpOnly cookie. Browser JavaScript can
 * never read it, so an injected script cannot steal it. Only server code (Server
 * Components, Server Actions, proxy.ts) touches it.
 */
export const SESSION_COOKIE = "carcux_session";

export async function getToken(): Promise<string | undefined> {
  return (await cookies()).get(SESSION_COOKIE)?.value;
}

/** Call only from Server Actions or Route Handlers. */
export async function setToken(token: string, maxAgeSeconds: number): Promise<void> {
  (await cookies()).set(SESSION_COOKIE, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: maxAgeSeconds,
  });
}

/** Call only from Server Actions or Route Handlers. */
export async function clearToken(): Promise<void> {
  (await cookies()).delete(SESSION_COOKIE);
}
