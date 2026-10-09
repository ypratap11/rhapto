import type { Metadata } from "next";
import { About } from "@/components/landing/About";

export const metadata: Metadata = {
  title: "What Rhapto does",
  description:
    "Rhapto finds jobs, tailors your resume from facts you have verified, and leaves the applying to you.",
};

/** The full pitch at its own stable URL (`README`/docs point here); `/` is the light landing. */
export default function AboutPage() {
  return <About />;
}
