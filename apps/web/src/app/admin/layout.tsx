import { headers } from "next/headers";
import { notFound } from "next/navigation";
import { isAdminAssertion } from "@/lib/admin/gate";

// The owner-only area. The API decides who is an admin; src/proxy.ts is the gate that makes the HTTP
// status a real 404 (a layout cannot: the root layout has already streamed a 200). This layout asks the
// same helper again as a second gate and renders the not-found page for anything but an admin.
export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  if (!(await isAdminAssertion((await headers()).get("cf-access-jwt-assertion")))) notFound();
  return <>{children}</>;
}
