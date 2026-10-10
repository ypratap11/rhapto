/** Fictional data for the homepage coach tour (Maya Chen, a data program manager). Wording that the
 * real coach shows comes from lib/coach/copy.ts, never from here; only the fictional values live in
 * this file. Plain module: no React, safe to import from server or client. */
export const TOUR_FILE = "maya-chen-resume.docx";
export const TOUR_ROLE = "Data Program Manager";

export const TOUR_TABS = [
  { value: "upload", label: "1 Upload" },
  { value: "role", label: "2 Role" },
  { value: "matches", label: "3 Top matches" },
  { value: "result", label: "4 Your resume" },
] as const;

/** `fit` against `minFit` goes through the coach's own `matchLabel`: 88 and 74 are Strong, 52 is Good. */
export const TOUR_JOBS = [
  { title: "Data Program Manager", company: "Contoso Robotics", fit: 88, minFit: 60 },
  { title: "Program Manager, Analytics", company: "Fabrikam Health", fit: 74, minFit: 60 },
  { title: "Technical Program Manager", company: "Tailspin Air", fit: 52, minFit: 60 },
] as const;

/** Two short changes, like the coach's "What changed" list (a reason, then the new line). No numbers. */
export const TOUR_CHANGES = [
  { reason: "Moved your reporting work to the top", after: "Led weekly pipeline reporting for the delivery teams at Northwind Labs." },
  { reason: "Used the job's words for stakeholder updates", after: "Ran stakeholder updates for the Acme Analytics data platform." },
] as const;
