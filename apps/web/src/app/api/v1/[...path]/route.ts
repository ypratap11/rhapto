const UPSTREAM = process.env.RHAPTO_API_INTERNAL_URL ?? "http://api:8000";

// Forwarded verbatim from the incoming request; the client's own `Authorization` is always
// dropped. `Cf-Access-Jwt-Assertion` is forwarded only when the request carries exactly one,
// syntactically well-formed compact JWS (`header.payload.signature`, see COMPACT_JWS below) --
// `Headers.get` joins repeated headers with ", ", which can never match that shape, so a request
// that appends a client-forged assertion alongside Cloudflare's genuine one is refused (403)
// rather than having both forwarded (fix-round finding S1: the previous comment here claimed the
// client's assertion was "dropped", which was false -- it was forwarded first in the joined list).
// range/accept-encoding are forwarded because the package-download endpoints may want them.
const FORWARD_REQUEST_HEADERS = ["accept", "content-type", "range", "accept-encoding"];

const CF_ASSERTION_HEADER = "cf-access-jwt-assertion";
// A compact JWS is exactly three base64url segments joined by ".". Cloudflare Access always sends
// one such value in one header; anything else -- absent, malformed, or two values joined by
// Headers.get's ", " -- is refused outright instead of sanitised or truncated.
const COMPACT_JWS = /^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/;

// undici's fetch accepts `duplex` to stream a request body through, but not every installed DOM
// lib types it yet; declaring our own permissive intersection avoids both an untyped call and a
// brittle `@ts-expect-error` that becomes an error itself the day the ambient lib catches up —
// verify with `pnpm typecheck` after writing this file.
type FetchInitWithDuplex = RequestInit & { duplex?: "half" };

async function proxy(request: Request, path: string[]): Promise<Response> {
  // Percent-decoded segments (e.g. a literal "..%2F..%2Fopenapi.json" arriving as one path
  // element) are re-encoded per segment before being joined, so a decoded "/" or ".." can never be
  // read as a directory separator by `new URL` -- it stays a single, harmless, percent-encoded
  // segment under /api/v1/ no matter what it decodes to (fix-round finding S2).
  const upstreamPath = path.map((segment) => encodeURIComponent(segment)).join("/");
  const upstreamUrl = new URL(`${UPSTREAM}/api/v1/${upstreamPath}${new URL(request.url).search}`);
  const headers = new Headers();
  for (const name of FORWARD_REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const assertion = request.headers.get(CF_ASSERTION_HEADER);
  if (assertion !== null) {
    if (!COMPACT_JWS.test(assertion)) {
      return new Response("invalid Cf-Access-Jwt-Assertion", { status: 403 });
    }
    headers.set("Cf-Access-Jwt-Assertion", assertion);
  }

  const init: FetchInitWithDuplex = {
    method: request.method,
    headers,
    body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
    duplex: request.body ? "half" : undefined,
  };
  const upstream = await fetch(upstreamUrl, init);

  const responseHeaders = new Headers(upstream.headers);
  if (upstream.headers.get("content-type")?.includes("text/event-stream")) {
    // `no-store` alone stops nothing here: it is a cache directive, and Next's own compression
    // middleware still gzips and buffers the stream because it has no `Content-Length` to bail out
    // on (fix-round finding C1). `no-transform` is the one directive that middleware honours to
    // skip compression, which is what actually keeps the stream unbuffered end to end.
    responseHeaders.set("Cache-Control", "no-store, no-transform");
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
