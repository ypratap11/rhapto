/** The coach's own wording, in one place. The step components under components/coach and the public
 * homepage tour (components/landing/coachTourData.ts) both import from here, so a copy change in the
 * coach changes the tour and CoachTour.test.tsx fails if a panel shows a string the coach does not. */
export const UPLOAD_TITLE = "Upload your resume";
export const UPLOAD_HINT = "A Word (.docx) file, up to 5 MB.";
export const CHOOSE_FILE = "Choose a file";

export function roleQuestion(name: string): string {
  return `Looks like you're aiming for: ${name}. Right?`;
}
export const ROLE_YES = "Yes, that's right";
export const ROLE_OTHER = "Something else";

export function matchesTitle(role: string): string {
  return `Your top matches for ${role}`;
}
export const TAILOR_THIS = "Tailor this one";

export const RESULT_TITLE = "Your tailored resume";
export const RESULT_READY = "Ready for you to read. Check it before you send it.";
export const DOWNLOAD_DOCX = "Download DOCX";
export const DOWNLOAD_PDF = "Download PDF";
export const WHAT_CHANGED = "What changed";
