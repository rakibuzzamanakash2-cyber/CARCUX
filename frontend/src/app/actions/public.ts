"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { ApiError } from "@/lib/api";
import { isUuid } from "@/lib/format";
import { clearPublicToken, publicApi, setPublicToken } from "@/lib/public";
import { REPORT_REASONS, type ActionState } from "@/lib/types";

type Token = { access_token: string; expires_in: number };

function failure(error: unknown, fallback: string): ActionState {
  return { ok: false, message: error instanceof ApiError ? error.detail : fallback };
}

function safeNext(value: FormDataEntryValue | null): string {
  const next = String(value ?? "");
  return next.startsWith("/public") && !next.startsWith("//") ? next : "/public";
}

export async function signUp(_prev: ActionState, formData: FormData): Promise<ActionState> {
  const body = {
    display_name: String(formData.get("display_name") ?? "").trim(),
    email: String(formData.get("email") ?? "").trim(),
    password: String(formData.get("password") ?? ""),
  };
  if (formData.get("agree") !== "on") return { ok: false, message: "Agree to the rules first." };
  if (body.password.length < 10) return { ok: false, message: "Use 10 characters or more." };
  try {
    await publicApi("/auth/signup", { method: "POST", body: JSON.stringify(body) });
  } catch (error) {
    return failure(error, "Could not sign you up. Try again.");
  }
  return {
    ok: true,
    message: `Check ${body.email} for a link to confirm your account. It works for 48 hours.`,
  };
}

export async function confirmEmail(_prev: ActionState, formData: FormData): Promise<ActionState> {
  const token = String(formData.get("token") ?? "");
  let t: Token;
  try {
    t = await publicApi<Token>("/auth/verify", { method: "POST", body: JSON.stringify({ token }) });
  } catch (error) {
    return failure(error, "Could not confirm. Try again.");
  }
  await setPublicToken(t.access_token, t.expires_in);
  redirect("/public?welcome=1");
}

export async function signIn(_prev: ActionState, formData: FormData): Promise<ActionState> {
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  let t: Token;
  try {
    t = await publicApi<Token>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  } catch (error) {
    return failure(error, "Could not sign you in. Try again.");
  }
  await setPublicToken(t.access_token, t.expires_in);
  redirect(safeNext(formData.get("next")));
}

export async function signOut(): Promise<void> {
  await clearPublicToken();
  redirect("/public");
}

export async function deleteAccount(_prev: ActionState, formData: FormData): Promise<ActionState> {
  try {
    await publicApi("/auth/delete", {
      method: "POST",
      body: JSON.stringify({ password: String(formData.get("password") ?? "") }),
    });
  } catch (error) {
    return failure(error, "Could not delete the account.");
  }
  await clearPublicToken();
  redirect("/public?deleted=1");
}

export async function setLike(postId: string, on: boolean): Promise<ActionState> {
  if (!isUuid(postId)) return { ok: false, message: "Unknown post." };
  try {
    await publicApi(`/posts/${postId}/like`, { method: on ? "PUT" : "DELETE" });
  } catch (error) {
    return failure(error, "Could not save your like.");
  }
  revalidatePath("/public", "layout");
  return { ok: true, message: on ? "Liked." : "Like removed." };
}

export async function addComment(
  postId: string,
  _prev: ActionState,
  formData: FormData,
): Promise<ActionState> {
  if (!isUuid(postId)) return { ok: false, message: "Unknown post." };
  const body = String(formData.get("body") ?? "").trim();
  if (body.length < 2) return { ok: false, message: "Write a comment first." };
  try {
    await publicApi(`/posts/${postId}/comments`, {
      method: "POST",
      body: JSON.stringify({ body }),
    });
  } catch (error) {
    return failure(error, "Could not post your comment.");
  }
  revalidatePath(`/public/posts/${postId}`);
  return { ok: true, message: "Comment posted." };
}

export async function reportComment(commentId: string, reason: string): Promise<ActionState> {
  if (!isUuid(commentId) || !REPORT_REASONS.some((r) => r.value === reason))
    return { ok: false, message: "Choose a reason." };
  try {
    await publicApi(`/comments/${commentId}/report`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    });
  } catch (error) {
    return failure(error, "Could not send the report.");
  }
  // No refresh: the thanks stays in view; a comment hidden by reports is gone on the next load.
  return { ok: true, message: "Thank you. A moderator will look at it." };
}

export async function deleteComment(commentId: string): Promise<ActionState> {
  if (!isUuid(commentId)) return { ok: false, message: "Unknown comment." };
  try {
    await publicApi(`/comments/${commentId}`, { method: "DELETE" });
  } catch (error) {
    return failure(error, "Could not delete the comment.");
  }
  revalidatePath("/public", "layout");
  return { ok: true, message: "Deleted." };
}

export async function addOpinion(
  eventId: string,
  _prev: ActionState,
  formData: FormData,
): Promise<ActionState> {
  if (!isUuid(eventId)) return { ok: false, message: "Unknown incident." };
  const body = String(formData.get("body") ?? "").trim();
  if (body.length < 2) return { ok: false, message: "Write your opinion first." };
  try {
    await publicApi(`/incidents/${eventId}/opinions`, {
      method: "POST",
      body: JSON.stringify({ body }),
    });
  } catch (error) {
    return failure(error, "Could not post your opinion.");
  }
  revalidatePath(`/public/incidents/${eventId}`);
  return { ok: true, message: "Opinion posted." };
}

export async function reportOpinion(opinionId: string, reason: string): Promise<ActionState> {
  if (!isUuid(opinionId) || !REPORT_REASONS.some((r) => r.value === reason))
    return { ok: false, message: "Choose a reason." };
  try {
    await publicApi(`/opinions/${opinionId}/report`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    });
  } catch (error) {
    return failure(error, "Could not send the report.");
  }
  return { ok: true, message: "Thank you. A moderator will look at it." };
}

export async function deleteOpinion(opinionId: string): Promise<ActionState> {
  if (!isUuid(opinionId)) return { ok: false, message: "Unknown opinion." };
  try {
    await publicApi(`/opinions/${opinionId}`, { method: "DELETE" });
  } catch (error) {
    return failure(error, "Could not delete the opinion.");
  }
  revalidatePath("/public", "layout");
  return { ok: true, message: "Deleted." };
}
