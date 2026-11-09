import { NextResponse, type NextRequest } from "next/server";
import { COMPACT_JWS } from "@/lib/access-assertion";

// /admin must answer a real HTTP 404 to anyone the API does not call an admin. The layout's
// notFound() cannot promise that: the root layout streams, so by the time the layout runs the 200
// status is already sent (verified against the built app: 200 with a "not found" body). A proxy runs
// before any rendering, so the status it returns is the status the browser gets. The layout check
// stays as a second gate; this one is what makes the status real.
export const config = { matcher: ["/admin", "/admin/:path*"] };

const NOT_FOUND = () => new NextResponse("Not Found", { status: 404, headers: { "content-type": "text/plain" } });

export async function proxy(request: NextRequest): Promise<NextResponse> {
  const assertion = request.headers.get("cf-access-jwt-assertion");
  if (assertion === null || !COMPACT_JWS.test(assertion)) return NOT_FOUND();
  try {
    const upstream = process.env.RHAPTO_API_INTERNAL_URL ?? "http://api:8000";
    const response = await fetch(`${upstream}/api/v1/admin/session`, {
      headers: { "Cf-Access-Jwt-Assertion": assertion },
      cache: "no-store",
    });
    if (response.status !== 200) return NOT_FOUND();
  } catch {
    return NOT_FOUND();
  }
  return NextResponse.next();
}
