import type { Metadata } from "next";
import { Suspense } from "react";
import { Coach } from "@/components/coach/Coach";

export const metadata: Metadata = { title: "Tailor a resume" };

/** The coach. `useSearchParams` (for `?task=`) needs a Suspense boundary in the App Router; confirm
 * against the guide in node_modules/next/dist/docs before changing it. */
export default function StartPage() {
  return (
    <Suspense fallback={null}>
      <Coach />
    </Suspense>
  );
}
