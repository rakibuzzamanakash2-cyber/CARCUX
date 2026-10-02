import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Optimistic check only: no session cookie means "go to login". The real check
// (token valid, account active, role) happens in lib/dal.ts against the backend.
const SESSION_COOKIE = "carcux_session";

export function proxy(request: NextRequest) {
  if (request.cookies.has(SESSION_COOKIE)) return NextResponse.next();

  const login = new URL("/login", request.url);
  if (request.nextUrl.pathname !== "/") login.searchParams.set("next", request.nextUrl.pathname);
  return NextResponse.redirect(login);
}

export const config = {
  // Everything except the login page, Next.js internals and static files.
  matcher: ["/((?!login|_next/static|_next/image|icon.png|carcux-logo-light.png).*)"],
};
