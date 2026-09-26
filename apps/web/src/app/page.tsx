import type { Metadata } from "next";
import { Landing } from "@/components/landing/Landing";

export const metadata: Metadata = {
  title: "Rhapto",
  description:
    "Rhapto finds jobs, tailors your resume from facts you have verified, and leaves the applying to you.",
};

/** The domain's front door. `TokenGate` lists "/" among its public routes, so this renders in
 * place of the app for anyone this instance lets through -- signed in or not -- rather than
 * handing a first-time invited person a wall of unfamiliar UI with no explanation. That is a
 * client-side routing choice, not a claim about who reaches Next.js at all: in an access-mode
 * deployment, Cloudflare Access still stops an unauthenticated stranger at the edge before this
 * page (or any page) ever runs, unless a separate, deliberate step opens "/" at that edge too. The
 * dashboard, previously mounted here, now lives at /dashboard. */
export default function HomePage() {
  return <Landing />;
}
