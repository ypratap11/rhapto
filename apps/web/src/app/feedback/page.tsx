import type { Metadata } from "next";
import { SurveyWizard } from "@/components/feedback/SurveyWizard";

export const metadata: Metadata = { title: "Feedback" };

export default function FeedbackPage() {
  return (
    <div className="mx-auto max-w-xl space-y-6">
      <div className="space-y-1">
        <h1 className="font-serif text-3xl">Tell us how it went</h1>
        <p className="text-sm text-muted-foreground">Seven short sections. Skip any of them, and come back after each session.</p>
      </div>
      <SurveyWizard />
    </div>
  );
}
