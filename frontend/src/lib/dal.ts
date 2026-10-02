import "server-only";

import { redirect } from "next/navigation";
import { cache } from "react";

import { api, ApiError } from "@/lib/api";
import { getToken } from "@/lib/session";
import type { Role, User } from "@/lib/types";

/**
 * Data Access Layer: the real authorization check.
 *
 * proxy.ts only checks that a cookie exists (fast, optimistic). Here the backend
 * validates the token on every request, including expiry, deactivation and role
 * changes, so a revoked user is locked out on their next click.
 *
 * `cache` dedupes the call within one request render.
 */
export const verifySession = cache(async (): Promise<User> => {
  if (!(await getToken())) redirect("/login");
  try {
    return await api<User>("/auth/me");
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/login?reason=expired");
    throw error;
  }
});

/** Require one of the given roles; anyone else is sent to the overview page. */
export async function requireRole(...roles: Role[]): Promise<User> {
  const user = await verifySession();
  if (!roles.includes(user.role)) redirect("/?denied=1");
  return user;
}
