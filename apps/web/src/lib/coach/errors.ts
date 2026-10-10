import { accessRequestLink } from "@/components/landing/access";
import { ApiError } from "@/lib/api/client";

export type NextAction = "reupload" | "role-picker" | "paste" | "request-access" | "settings" | "feedback" | "retry";
export type CoachError = { message: string; next: NextAction; link?: { label: string; href: string } };
export type CoachWhere = "upload" | "import" | "tailor" | "jobs";

export const MAX_RESUME_BYTES = 5 * 1024 * 1024;
export const DOCX_MESSAGE =
  "Rhapto reads Word (.docx) files up to 5 MB. In Word or Google Docs, use Save as / Download as .docx";

const GENERIC = "Something went wrong on our side. Try again in a moment.";
const RUN_DID_NOT_FINISH = "The run didn't finish. Try again, or pick another job.";

/** The only server sentences that may reach the screen verbatim: they are written for the tester
 * (`trial_limit_message`, `SHARED_KEY_REJECTED_MESSAGE`, `KEY_UNREADABLE_MESSAGE` in the API) and each
 * has the same way forward, Settings. Anything else a task or a provider says is not shown.
 * The two "Your ... key" sentences are `user_key_message` in apps/api/src/rhapto/worker/tasks.py, which
 * must change in step with these patterns. */
const KEY_PROVIDERS = "(?:OpenAI|Anthropic|Google Gemini|Groq|OpenRouter)";
const SETTINGS_SENTENCES: RegExp[] = [
  /^You have used all \d+ free tailoring runs? on this instance\. Add your own provider API key in Settings to keep going\.$/,
  /^This instance does not offer free runs\. Add your own provider API key in Settings to use it\.$/,
  /^This instance's shared LLM key was refused by its provider\. Add your own key in Settings to keep going, or ask whoever runs this instance to check it\.$/,
  /^Your stored API key can no longer be decrypted \(the server secret changed\)\. Re-enter it in Settings\.$/,
  new RegExp(`^Your ${KEY_PROVIDERS} key was refused\\. It may have expired or been revoked\\. Paste a new key in Settings, then try again\\.$`),
  new RegExp(`^Your ${KEY_PROVIDERS} account is out of credit\\. Add credit with ${KEY_PROVIDERS} or paste a different key in Settings\\.$`),
];
const SETTINGS_LINK = { label: "Open Settings", href: "/settings" };
export const isSettingsSentence = (text: string) => SETTINGS_SENTENCES.some((re) => re.test(text));

/** Client-side pre-check, so a PDF never costs a request. The server enforces the same two rules. */
export function checkResumeFile(file: { name: string; size: number }): CoachError | null {
  if (!file.name.toLowerCase().endsWith(".docx") || file.size > MAX_RESUME_BYTES) {
    return { message: DOCX_MESSAGE, next: "reupload" };
  }
  return null;
}

/** Spec 3.4: plain words, always one way forward. A status code, a rule id or a provider name never
 * reaches the screen; the only server text shown verbatim is a known plain sentence (see `SETTINGS_SENTENCES`). */
export function describeCoachError(error: unknown, where: CoachWhere): CoachError {
  if (error instanceof ApiError) {
    const code = typeof error.problem?.code === "string" ? error.problem.code : null;
    if (error.status === 403) {
      const access = accessRequestLink();
      return { message: "Rhapto is invite-only right now", next: "request-access", link: { label: "Request access", href: access.href } };
    }
    if (error.status === 409 && code === "trial_limit_reached") {
      return isSettingsSentence(error.message)
        ? { message: error.message, next: "settings", link: SETTINGS_LINK }
        : { message: "You have used your free runs. Add your own provider API key in Settings to keep going.", next: "settings", link: SETTINGS_LINK };
    }
    if (error.status === 409 && (code === "llm_not_configured" || code === "llm_key_unreadable")) {
      return { message: "Rhapto isn't set up to tailor yet", next: "feedback", link: { label: "Tell us", href: "/feedback" } };
    }
    if (error.status === 422 && where === "upload") return { message: DOCX_MESSAGE, next: "reupload" };
    if (error.status === 422 && where === "import") return { message: "We couldn't read the roles in this resume", next: "role-picker" };
    if (error.status === 422 && where === "tailor") return { message: "We couldn't use your resume for this job. Try another job.", next: "retry" };
    return { message: GENERIC, next: "retry" };
  }
  if (error instanceof Error && where === "tailor" && !(error instanceof TypeError)) {
    // A failed task's reason: known plain sentences verbatim, never an exception class or a provider body.
    if (isSettingsSentence(error.message)) return { message: error.message, next: "settings", link: SETTINGS_LINK };
    return { message: RUN_DID_NOT_FINISH, next: "retry" };
  }
  return { message: GENERIC, next: "retry" };
}
