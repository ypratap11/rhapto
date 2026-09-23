import type { Metadata } from "next";
import { Landing } from "@/components/landing/Landing";

export const metadata: Metadata = {
  title: "What Rhapto does",
  description:
    "Rhapto finds jobs, tailors your resume from facts you have verified, and leaves the applying to you.",
};

/** The landing page at its own stable URL, so it can be linked to and read by someone who is
 * already connected. `TokenGate` renders the same component at `/` for anyone who is not. */
export default function AboutPage() {
  return <Landing />;
}
