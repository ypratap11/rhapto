// Compact JWS look-alikes (header.payload.signature). The stub reads the payload only and does not
// verify a signature: the real API does that, and this stack has no Cloudflare.
function jws(payload: Record<string, unknown>): string {
  const part = (value: unknown) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${part({ alg: "none", typ: "JWT" })}.${part(payload)}.c3R1Yg`;
}

export const ADMIN_ASSERTION = jws({ email: "owner@example.com", admin: true });
export const NON_ADMIN_ASSERTION = jws({ email: "someone@example.com", admin: false });
