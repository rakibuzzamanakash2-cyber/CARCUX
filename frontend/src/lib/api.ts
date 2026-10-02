import "server-only";

import { getToken } from "@/lib/session";

/** Backend base URL, read on the server only. Never exposed to the browser. */
export const API_URL = process.env.CARCUX_API_URL ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(`${status}: ${detail}`);
  }
}

/** Turn FastAPI error bodies (string or validation list) into one readable message. */
function readableDetail(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      return detail
        .map((d: { loc?: unknown[]; msg?: string }) => {
          const field = Array.isArray(d.loc) ? d.loc[d.loc.length - 1] : undefined;
          const msg = (d.msg ?? "invalid").replace(/^Value error, /, "");
          return field ? `${String(field).replace(/_/g, " ")}: ${msg}` : msg;
        })
        .join("; ");
    }
  }
  return fallback;
}

/**
 * Call the CARCUX backend from server code and return the raw response. Adds the
 * session token when present. Sends JSON unless the body is FormData (multipart,
 * where fetch sets the boundary itself). Throws ApiError for non-2xx responses.
 */
export async function apiFetch(
  path: string,
  init: RequestInit & { auth?: boolean } = {},
): Promise<Response> {
  const { auth = true, headers, ...rest } = init;
  const token = auth ? await getToken() : undefined;
  const isForm = rest.body instanceof FormData;

  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...rest,
      cache: "no-store",
      headers: {
        ...(isForm ? {} : { "Content-Type": "application/json" }),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...headers,
      },
    });
  } catch {
    throw new ApiError(503, "The CARCUX backend is not reachable. Is it running?");
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(response.status, readableDetail(body, response.statusText));
  }
  return response;
}

/** Call the backend and parse the JSON body. See apiFetch. */
export async function api<T>(
  path: string,
  init: RequestInit & { auth?: boolean } = {},
): Promise<T> {
  return (await (await apiFetch(path, init)).json()) as T;
}
