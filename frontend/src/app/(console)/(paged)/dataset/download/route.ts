import { apiFetch, ApiError } from "@/lib/api";

/**
 * The dataset zip, fetched with the session token (the browser cannot call the
 * backend itself). The backend allows admins only and records the export.
 */
export async function GET(request: Request) {
  const all = new URL(request.url).searchParams.get("all") === "1";
  try {
    const upstream = await apiFetch(`/dataset/export${all ? "?include_unlinked=true" : ""}`);
    return new Response(upstream.body, {
      headers: {
        "Content-Type": "application/zip",
        "Content-Disposition":
          upstream.headers.get("Content-Disposition") ?? 'attachment; filename="carcux-bd.zip"',
        "Cache-Control": "no-store",
      },
    });
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 502;
    return new Response(status === 403 ? "Admins only" : "Could not export", {
      status: status === 401 || status === 403 ? status : 502,
    });
  }
}
