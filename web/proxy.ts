import { NextResponse, type NextRequest } from "next/server";

import { GATE_COOKIE, expectedToken } from "@/lib/gate";

// Next 16 renamed middleware to proxy (node_modules/next/dist/docs, upgrading/version-16.md).
// An optimistic gate in front of every page, server action and route handler.
export async function proxy(request: NextRequest) {
  const expected = await expectedToken();
  if (expected && request.cookies.get(GATE_COOKIE)?.value === expected) {
    return NextResponse.next();
  }
  return NextResponse.redirect(new URL("/login", request.url));
}

export const config = {
  // Public assets the login page needs: the logo and the generated app icons.
  matcher: ["/((?!login|_next/static|_next/image|icon.png|apple-icon.png|logo.png).*)"],
};
