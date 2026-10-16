"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { api, ApiError } from "@/lib/api";
import { requireRole } from "@/lib/dal";
import { isUuid } from "@/lib/format";
import { PAGE_KINDS, type ActionState, type OfficialPageDetail } from "@/lib/types";

const KINDS = new Set<string>(PAGE_KINDS.map((k) => k.value));

function failure(error: unknown, fallback: string): ActionState {
  return { ok: false, message: error instanceof ApiError ? error.detail : fallback };
}

function text(formData: FormData, key: string): string | null {
  const value = String(formData.get(key) ?? "").trim();
  return value || null;
}

function pageFields(formData: FormData) {
  return {
    name: text(formData, "name"),
    name_bn: text(formData, "name_bn"),
    kind: text(formData, "kind"),
    description: text(formData, "description"),
    website: text(formData, "website"),
    contact_email: text(formData, "contact_email"),
  };
}

function refresh(slug?: string) {
  revalidatePath("/official-pages");
  if (slug) revalidatePath(`/official-pages/${slug}`);
}

export async function createPage(_prev: ActionState, formData: FormData): Promise<ActionState> {
  await requireRole("admin");
  const body = { slug: text(formData, "slug"), ...pageFields(formData) };
  if (!body.kind || !KINDS.has(body.kind)) return { ok: false, message: "Choose what it is." };
  let page: OfficialPageDetail;
  try {
    page = await api<OfficialPageDetail>("/official-pages", {
      method: "POST",
      body: JSON.stringify(body),
    });
  } catch (error) {
    return failure(error, "Could not create the page.");
  }
  refresh();
  redirect(`/official-pages/${page.slug}?created=1`);
}

export async function updatePage(
  pageId: string,
  slug: string,
  _prev: ActionState,
  formData: FormData,
): Promise<ActionState> {
  await requireRole("admin");
  if (!isUuid(pageId)) return { ok: false, message: "Unknown page." };
  const fields = pageFields(formData);
  if (!fields.kind || !KINDS.has(fields.kind)) return { ok: false, message: "Choose what it is." };
  try {
    await api(`/official-pages/${pageId}`, { method: "PATCH", body: JSON.stringify(fields) });
  } catch (error) {
    return failure(error, "Could not save the page.");
  }
  refresh(slug);
  return { ok: true, message: "Saved." };
}

export async function uploadLetter(
  pageId: string,
  slug: string,
  _prev: ActionState,
  formData: FormData,
): Promise<ActionState> {
  await requireRole("admin");
  const file = formData.get("file");
  if (!isUuid(pageId)) return { ok: false, message: "Unknown page." };
  if (!(file instanceof File) || file.size === 0) return { ok: false, message: "Choose the file." };
  if (file.size > 10 * 1024 * 1024) return { ok: false, message: "The file is larger than 10 MB." };
  const body = new FormData();
  body.set("file", file, file.name);
  try {
    await api(`/official-pages/${pageId}/document`, { method: "POST", body });
  } catch (error) {
    return failure(error, "Could not upload the letter.");
  }
  refresh(slug);
  return { ok: true, message: "Letter stored." };
}

export async function verifyPage(
  pageId: string,
  slug: string,
  _prev: ActionState,
  formData: FormData,
): Promise<ActionState> {
  await requireRole("admin");
  const method = text(formData, "method");
  const note = text(formData, "note") ?? "";
  if (!isUuid(pageId)) return { ok: false, message: "Unknown page." };
  if (method !== "official_email" && method !== "official_letter")
    return { ok: false, message: "Choose how the office confirmed it." };
  if (note.length < 10)
    return { ok: false, message: "Say what you checked (10 characters or more)." };
  try {
    await api(`/official-pages/${pageId}/verify`, {
      method: "POST",
      body: JSON.stringify({ method, note }),
    });
  } catch (error) {
    return failure(error, "Could not verify the page.");
  }
  refresh(slug);
  return { ok: true, message: "Verified." };
}

export async function suspendPage(
  pageId: string,
  slug: string,
  _prev: ActionState,
  formData: FormData,
): Promise<ActionState> {
  await requireRole("admin");
  const reason = text(formData, "reason") ?? "";
  if (!isUuid(pageId)) return { ok: false, message: "Unknown page." };
  if (reason.length < 10) return { ok: false, message: "Give the reason (10 characters or more)." };
  try {
    await api(`/official-pages/${pageId}/suspend`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    });
  } catch (error) {
    return failure(error, "Could not suspend the page.");
  }
  refresh(slug);
  return { ok: true, message: "Suspended." };
}

export async function reinstatePage(pageId: string, slug: string): Promise<ActionState> {
  await requireRole("admin");
  if (!isUuid(pageId)) return { ok: false, message: "Unknown page." };
  try {
    await api(`/official-pages/${pageId}/reinstate`, { method: "POST" });
  } catch (error) {
    return failure(error, "Could not reinstate the page.");
  }
  refresh(slug);
  return { ok: true, message: "Reinstated." };
}

export async function addOfficial(
  pageId: string,
  slug: string,
  _prev: ActionState,
  formData: FormData,
): Promise<ActionState> {
  await requireRole("admin");
  if (!isUuid(pageId)) return { ok: false, message: "Unknown page." };
  const body = {
    full_name: text(formData, "full_name"),
    email: text(formData, "email"),
    password: String(formData.get("password") ?? ""),
  };
  try {
    await api(`/official-pages/${pageId}/members`, { method: "POST", body: JSON.stringify(body) });
  } catch (error) {
    return failure(error, "Could not create the account.");
  }
  refresh(slug);
  revalidatePath("/users");
  return { ok: true, message: `Account created for ${body.email}.` };
}
