import { describe, expect, it } from "vitest";
import { ApiError } from "@/lib/api/client";
import { ACCESS_REQUEST_MAILTO, ACCESS_REQUEST_URL } from "@/components/landing/access";
import { checkResumeFile, describeCoachError, DOCX_MESSAGE, MAX_RESUME_BYTES } from "./errors";

const problem = (status: number, extra: Record<string, unknown> = {}) => ({ title: "x", status, ...extra });

describe("checkResumeFile", () => {
  it("accepts a .docx up to 5 MB", () => {
    expect(checkResumeFile({ name: "Maya_Chen.docx", size: MAX_RESUME_BYTES })).toBeNull();
    expect(checkResumeFile({ name: "RESUME.DOCX", size: 10 })).toBeNull();
  });
  it("rejects a PDF and an oversized file with the Save-as sentence", () => {
    for (const file of [{ name: "cv.pdf", size: 10 }, { name: "cv.docx", size: MAX_RESUME_BYTES + 1 }]) {
      const error = checkResumeFile(file)!;
      expect(error.message).toBe(DOCX_MESSAGE);
      expect(error.next).toBe("reupload");
    }
    expect(DOCX_MESSAGE).toMatch(/Word \(\.docx\) files up to 5 MB.*Save as \/ Download as \.docx/);
  });
});

describe("describeCoachError (spec 3.4, one row per case, always one way forward)", () => {
  it("upload 422 -> the .docx sentence, re-upload", () => {
    expect(describeCoachError(new ApiError(422, problem(422), "x"), "upload")).toEqual({ message: DOCX_MESSAGE, next: "reupload" });
  });
  it("import 422 -> we could not read the roles, role picker", () => {
    expect(describeCoachError(new ApiError(422, problem(422), "x"), "import")).toEqual({
      message: "We couldn't read the roles in this resume",
      next: "role-picker",
    });
  });
  it("403 -> invite-only with the request-access link, anywhere", () => {
    const error = describeCoachError(new ApiError(403, problem(403, { detail: "this instance is invite-only" }), "x"), "upload");
    expect(error.message).toBe("Rhapto is invite-only right now");
    expect(error.next).toBe("request-access");
    expect(error.link?.href).toBe(ACCESS_REQUEST_URL || ACCESS_REQUEST_MAILTO);
  });
  it("409 trial_limit_reached -> the server's trial sentence, Settings", () => {
    const sentence = "You have used all 3 free tailoring runs on this instance. Add your own provider API key in Settings to keep going.";
    const error = describeCoachError(new ApiError(409, problem(409, { detail: sentence, code: "trial_limit_reached" }), "x"), "tailor");
    expect(error).toEqual({ message: sentence, next: "settings", link: { label: "Open Settings", href: "/settings" } });
  });
  it("409 llm_not_configured -> Rhapto isn't set up to tailor yet, Feedback", () => {
    const error = describeCoachError(new ApiError(409, problem(409, { code: "llm_not_configured" }), "x"), "tailor");
    expect(error.message).toBe("Rhapto isn't set up to tailor yet");
    expect(error.next).toBe("feedback");
    expect(error.link?.href).toBe("/feedback");
  });
  it("a failed task's raw exception text is never shown: a plain sentence and retry instead", () => {
    for (const raw of ["MalformedOutputError: model returned 3 tool calls, expected 1", "LLMBudgetExceeded: spent 4.2 of 4.0", "The model returned an unreadable answer."]) {
      const out = describeCoachError(new Error(raw), "tailor");
      expect(out).toEqual({ message: "The run didn't finish. Try again, or pick another job.", next: "retry" });
    }
  });
  it("a provider error body never reaches the screen, whether it is an Error or an ApiError", () => {
    const body = 'AuthenticationError: Error code: 401 - {"error": {"message": "Incorrect API key provided", "type": "invalid_request_error"}} anthropic openrouter';
    for (const error of [new Error(body), new ApiError(422, problem(422, { detail: body }), body)]) {
      const out = describeCoachError(error, "tailor");
      expect(out.message).not.toMatch(/401|Error code|anthropic|openrouter|AuthenticationError|\{/i);
      expect(out.next).toBe("retry");
    }
  });
  it("the known plain task sentences are shown verbatim, with the Settings way forward", () => {
    for (const sentence of [
      "You have used all 5 free tailoring runs on this instance. Add your own provider API key in Settings to keep going.",
      "This instance's shared LLM key was refused by its provider. Add your own key in Settings to keep going, or ask whoever runs this instance to check it.",
      "Your stored API key can no longer be decrypted (the server secret changed). Re-enter it in Settings.",
    ]) {
      expect(describeCoachError(new Error(sentence), "tailor")).toEqual({ message: sentence, next: "settings", link: { label: "Open Settings", href: "/settings" } });
    }
  });
  it("a 409 trial code with a sentence we do not know is not shown verbatim either", () => {
    const out = describeCoachError(new ApiError(409, problem(409, { code: "trial_limit_reached", detail: "OpenRouter credit balance 0.02" }), "x"), "tailor");
    expect(out.message).not.toMatch(/openrouter|0\.02/i);
    expect(out.next).toBe("settings");
  });
  it("a 5xx or a network failure never leaks a status code", () => {
    for (const error of [new ApiError(500, problem(500), "HTTP 500"), new TypeError("Failed to fetch")]) {
      const out = describeCoachError(error, "jobs");
      expect(out.message).toBe("Something went wrong on our side. Try again in a moment.");
      expect(out.message).not.toMatch(/500|fetch/i);
      expect(out.next).toBe("retry");
    }
  });
});
