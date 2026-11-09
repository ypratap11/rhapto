import { NextResponse, type NextRequest } from "next/server";
import { isAdminAssertion } from "@/lib/admin/gate";

// /admin must answer a real HTTP 404 to anyone the API does not call an admin. The layout's
// notFound() cannot promise that: the root layout streams, so by the time the layout runs the 200
// status is already sent (verified against the built app: 200 with a "not found" body). A proxy runs
// before any rendering, so the status it returns is the status the browser gets. The layout check
// stays as a second gate; both ask the same helper.
export const config = { matcher: ["/admin", "/admin/:path*"] };

export async function proxy(request: NextRequest): Promise<NextResponse> {
  if (await isAdminAssertion(request.headers.get("cf-access-jwt-assertion"))) return NextResponse.next();
  return new NextResponse("Not Found", { status: 404, headers: { "content-type": "text/plain" } });
}
