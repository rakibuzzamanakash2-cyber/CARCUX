import { api, apiFetch, ApiError } from "@/lib/api";
import type { OfficialPage } from "@/lib/types";

/** The verification letter, for admins (the backend refuses anyone else). */
export async function GET(_request: Request, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  try {
    const page = await api<OfficialPage>(`/official-pages/by-slug/${encodeURIComponent(slug)}`);
    const upstream = await apiFetch(`/official-pages/${page.id}/document`);
    return new Response(upstream.body, {
      headers: {
        "Content-Type": upstream.headers.get("Content-Type") ?? "application/octet-stream",
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Disposition": "inline",
      },
    });
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 502;
    return new Response(status === 401 ? "Sign in again" : "Not found", {
      status: status === 401 ? 401 : 404,
    });
  }
}
