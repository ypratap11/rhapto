// A compact JWS is exactly three base64url segments joined by ".". Cloudflare Access always sends
// one such value in one header; anything else -- absent, malformed, or two values joined by
// Headers.get's ", " -- is refused outright instead of sanitised or truncated.
// Lives here, not in the proxy route file: Next rejects non-handler exports from route files.
export const COMPACT_JWS = /^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/;
