"use server";

import { revalidatePath } from "next/cache";

import { api, ApiError } from "@/lib/api";
import { requireRole } from "@/lib/dal";
import { ROLES, type ActionState, type Role, type User } from "@/lib/types";

const VALID_ROLES = new Set<string>(ROLES.map((r) => r.value));

function failure(error: unknown, fallback: string): ActionState {
  return { ok: false, message: error instanceof ApiError ? error.detail : fallback };
}

export async function createUser(_prev: ActionState, formData: FormData): Promise<ActionState> {
  // Server Actions are public endpoints: always re-check authorization here.
  await requireRole("admin");

  const role = String(formData.get("role") ?? "");
  const email = String(formData.get("email") ?? "").trim();
  const full_name = String(formData.get("full_name") ?? "").trim();
  if (!VALID_ROLES.has(role)) return { ok: false, message: "Choose a role." };

  const body = { email, full_name, password: String(formData.get("password") ?? ""), role };
  try {
    const user = await api<User>("/users", { method: "POST", body: JSON.stringify(body) });
    revalidatePath("/users");
    return { ok: true, message: `Account created for ${user.email}.` };
  } catch (error) {
    return failure(error, "Could not create the account.");
  }
}

export async function updateUser(
  userId: string,
  changes: { role?: Role; is_active?: boolean },
): Promise<ActionState> {
  await requireRole("admin");

  if (changes.role !== undefined && !VALID_ROLES.has(changes.role)) {
    return { ok: false, message: "Unknown role." };
  }
  try {
    await api<User>(`/users/${encodeURIComponent(userId)}`, {
      method: "PATCH",
      body: JSON.stringify(changes),
    });
    revalidatePath("/users");
    return { ok: true, message: "Saved." };
  } catch (error) {
    return failure(error, "Could not save the change.");
  }
}
