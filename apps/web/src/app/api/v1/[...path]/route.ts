const UPSTREAM = process.env.RHAPTO_API_INTERNAL_URL ?? "http://api:8000";

// Forwarded verbatim from the incoming request; the client's own `Authorization` and any
// client-supplied `Cf-Access-Jwt-Assertion` are dropped so the only assertion that can ever reach
// the API is the one Cloudflare's edge attached to *this* request. range/accept-encoding are
// forwarded because the package-download endpoints may want them.
const FORWARD_REQUEST_HEADERS = ["accept", "content-type", "range", "accept-encoding"];

// undici's fetch accepts `duplex` to stream a request body through, but not every installed DOM
// lib types it yet; declaring our own permissive intersection avoids both an untyped call and a
// brittle `@ts-expect-error` that becomes an error itself the day the ambient lib catches up —
// verify with `pnpm typecheck` after writing this file.
type FetchInitWithDuplex = RequestInit & { duplex?: "half" };

async function proxy(request: Request, path: string[]): Promise<Response> {
  if (path.some((segment) => segment === "..")) {
    return new Response("invalid path", { status: 400 });
  }
  const upstreamUrl = new URL(`${UPSTREAM}/api/v1/${path.join("/")}${new URL(request.url).search}`);
  const headers = new Headers();
  for (const name of FORWARD_REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const assertion = request.headers.get("cf-access-jwt-assertion");
  if (assertion) headers.set("Cf-Access-Jwt-Assertion", assertion);

  const init: FetchInitWithDuplex = {
    method: request.method,
    headers,
    body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
    duplex: request.body ? "half" : undefined,
  };
  const upstream = await fetch(upstreamUrl, init);

  const responseHeaders = new Headers(upstream.headers);
  if (upstream.headers.get("content-type")?.includes("text/event-stream")) {
    responseHeaders.set("Cache-Control", "no-store");
    responseHeaders.set("X-Accel-Buffering", "no");
  }
  return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
}

export async function GET(request: Request, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(request, (await params).path);
}
export async function POST(request: Request, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(request, (await params).path);
}
export async function PUT(request: Request, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(request, (await params).path);
}
export async function PATCH(request: Request, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(request, (await params).path);
}
export async function DELETE(request: Request, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(request, (await params).path);
}
