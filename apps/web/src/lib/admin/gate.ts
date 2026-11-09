import { COMPACT_JWS } from "@/lib/access-assertion";

/**
 * The one admin decision, shared by proxy.ts (which makes the HTTP status real) and
 * app/admin/layout.tsx (a second gate). True only when the assertion is one well-formed compact JWS
 * and the API answers exactly 200 for it. Everything else, including a missing assertion, a non-200,
 * a hung or unreachable API, is false: fail closed.
 */
export async function isAdminAssertion(assertion: string | null): Promise<boolean> {
  if (assertion === null || !COMPACT_JWS.test(assertion)) return false;
  try {
    const upstream = process.env.RHAPTO_API_INTERNAL_URL ?? "http://api:8000";
    const response = await fetch(`${upstream}/api/v1/admin/session`, {
      headers: { "Cf-Access-Jwt-Assertion": assertion },
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    return response.status === 200;
  } catch {
    return false;
  }
}
