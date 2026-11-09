import { headers } from "next/headers";
import { notFound } from "next/navigation";
import { COMPACT_JWS } from "@/lib/access-assertion";

// The owner-only area. The API decides who is an admin; this layout only asks and turns anything
// but a 200 into a real HTTP 404. No loading.tsx and no Suspense above this check: a streaming
// shell would commit a 200 before notFound() could run.
export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  const assertion = (await headers()).get("cf-access-jwt-assertion");
  if (assertion === null || !COMPACT_JWS.test(assertion)) notFound();
  let status: number;
  try {
    const upstream = process.env.RHAPTO_API_INTERNAL_URL ?? "http://api:8000";
    const response = await fetch(`${upstream}/api/v1/admin/session`, {
      headers: { "Cf-Access-Jwt-Assertion": assertion },
      cache: "no-store",
    });
    status = response.status;
  } catch {
    notFound();
  }
  if (status !== 200) notFound();
  return <>{children}</>;
}
