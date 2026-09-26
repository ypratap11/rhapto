import type { Metadata } from "next";
import { Landing } from "@/components/landing/Landing";

export const metadata: Metadata = {
  title: "What Rhapto does",
  description:
    "Rhapto finds jobs, tailors your resume from facts you have verified, and leaves the applying to you.",
};

/** The landing page at its own stable URL: a stable link that `README`/docs point at, readable by
 * someone already connected. `/` now renders this same component for everyone -- both routes
 * rendering `Landing` is intended, not duplication to remove. */
export default function AboutPage() {
  return <Landing />;
}
