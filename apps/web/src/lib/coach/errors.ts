import { accessRequestLink } from "@/components/landing/access";
import { ApiError } from "@/lib/api/client";

export type NextAction = "reupload" | "role-picker" | "paste" | "request-access" | "settings" | "feedback" | "retry";
export type CoachError = { message: string; next: NextAction; link?: { label: string; href: string } };
export type CoachWhere = "upload" | "import" | "tailor" | "jobs";

export const MAX_RESUME_BYTES = 5 * 1024 * 1024;
export const DOCX_MESSAGE =
  "Rhapto reads Word (.docx) files up to 5 MB. In Word or Google Docs, use Save as / Download as .docx";

const GENERIC = "Something went wrong on our side. Try again in a moment.";

/** Client-side pre-check, so a PDF never costs a request. The server enforces the same two rules. */
export function checkResumeFile(file: { name: string; size: number }): CoachError | null {
  if (!file.name.toLowerCase().endsWith(".docx") || file.size > MAX_RESUME_BYTES) {
    return { message: DOCX_MESSAGE, next: "reupload" };
  }
  return null;
}

/** Spec 3.4: plain words, always one way forward. A status code, a rule id or a provider name never
 * reaches the screen; the only server text shown verbatim is the trial sentence (it contains one
 * integer and nothing about the deployment, see `trial_limit_message`) and a failed task's reason. */
export function describeCoachError(error: unknown, where: CoachWhere): CoachError {
  if (error instanceof ApiError) {
    const code = typeof error.problem?.code === "string" ? error.problem.code : null;
    if (error.status === 403) {
      const access = accessRequestLink();
      return { message: "Rhapto is invite-only right now", next: "request-access", link: { label: "Request access", href: access.href } };
    }
    if (error.status === 409 && code === "trial_limit_reached") {
      return { message: error.message, next: "settings", link: { label: "Open Settings", href: "/settings" } };
    }
    if (error.status === 409 && (code === "llm_not_configured" || code === "llm_key_unreadable")) {
      return { message: "Rhapto isn't set up to tailor yet", next: "feedback", link: { label: "Tell us", href: "/feedback" } };
    }
    if (error.status === 422 && where === "upload") return { message: DOCX_MESSAGE, next: "reupload" };
    if (error.status === 422 && where === "import") return { message: "We couldn't read the roles in this resume", next: "role-picker" };
    if (error.status === 422 && where === "tailor") return { message: error.message, next: "reupload" };
    return { message: GENERIC, next: "retry" };
  }
  if (error instanceof Error && where === "tailor" && !(error instanceof TypeError)) {
    return { message: error.message, next: "retry" }; // a failed task's reason
  }
  return { message: GENERIC, next: "retry" };
}
