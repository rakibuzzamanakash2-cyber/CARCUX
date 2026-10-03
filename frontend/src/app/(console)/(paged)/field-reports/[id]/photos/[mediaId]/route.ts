import { apiFetch, ApiError } from "@/lib/api";
import { isUuid } from "@/lib/format";

/**
 * Serves a report photo to the signed-in user. The browser cannot call the backend
 * itself (the token lives in an httpOnly cookie), so this handler fetches the photo
 * with the session token. The backend decides who may see it.
 */
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string; mediaId: string }> },
) {
  const { id, mediaId } = await params;
  if (!isUuid(id) || !isUuid(mediaId)) return new Response("Not found", { status: 404 });

  try {
    const upstream = await apiFetch(`/field-reports/${id}/media/${mediaId}`);
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
      status: status === 401 ? 401 : status === 503 ? 503 : 404,
    });
  }
}
