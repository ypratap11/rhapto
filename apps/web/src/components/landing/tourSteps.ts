/** The product tour's content and geometry. No React, no "use client": pure data plus one pure
 * function, so the component stays small and the maths is testable without a DOM.
 *
 * Copy is the owner-approved tour copy, with the truth edits the architecture gate required
 * (`.superpowers/sdd/landing-product-tour/architecture.md`, condition 12): steps 1, 2, 3, 9 and 12
 * and the outro. Every fact here is a fact of ONE captured run (29 September 2026, fictional demo
 * profile "Maya Chen", real jobs, real AI run). None of it is a guarantee about every run, so keep
 * it that way when editing: do not turn a fact of the capture into a promise.
 *
 * Captions are structured (`Seg[]`), never HTML strings, so nothing here is ever injected as markup. */

/** A run of caption text; `bold` marks the words the reader should look at. */
export type Seg = { text: string; bold?: boolean };

export const TOUR_W = 1443;
export const TOUR_H = 758;

export const CHAPTERS = ["Your record", "Find", "Tailor", "Review", "Apply"] as const;

type Raw = {
  /** Chapter index into CHAPTERS. */
  c: number;
  /** File stem under /tour/, e.g. "01" is /tour/01.webp. */
  img: string;
  /** The path shown in the fake browser bar. */
  url: string;
  /** Hotspot in screenshot pixels (1443 x 758). */
  x: number;
  y: number;
  /** How far to lean in toward the hotspot. */
  zoom: number;
  /** Where the caption card sits, as fractions [left, top] of the picture (desktop only). */
  at: readonly [number, number];
  title: string;
  body: readonly Seg[];
};

export type TourStep = Raw & {
  /** CSS `translate()` of the zoomed picture, as percentages of the frame. */
  tx: number;
  ty: number;
  /** Hotspot position as a percentage of the frame, after the zoom. */
  hx: number;
  hy: number;
};

const RAW: readonly Raw[] = [
  {
    c: 0, img: "01", url: "/profile · Blocks", x: 1000, y: 490, zoom: 1.25, at: [0.05, 0.3],
    title: "Maya writes her career down once",
    body: [
      { text: "Her record lives in " },
      { text: "blocks", bold: true },
      {
        text: ": short facts about her work at Northwind Labs, Acme Analytics and Globex. Every line in a resume Rhapto writes for her has to cite one of these.",
      },
    ],
  },
  {
    c: 0, img: "02", url: "/profile · Blocks", x: 1305, y: 490, zoom: 1.35, at: [0.05, 0.3],
    title: "Numbers wait for her sign-off",
    body: [
      { text: "Each block is marked verified or not. Her 2021 claim of a " },
      { text: "42% forecast improvement", bold: true },
      { text: " isn't verified yet, so Rhapto's checks won't let that number through. Watch for it later." },
    ],
  },
  {
    c: 1, img: "03", url: "/dashboard", x: 560, y: 110, zoom: 1.15, at: [0.42, 0.04],
    title: "Rhapto searches the market for her",
    body: [
      { text: "Her first search pulled " },
      { text: "28 live jobs", bold: true },
      {
        text: " from job boards and company career pages, and scored each one against her two career tracks and her location.",
      },
    ],
  },
  {
    c: 1, img: "04", url: "/jobs", x: 1230, y: 450, zoom: 1.3, at: [0.48, 0.43],
    title: "Every job gets a fit score",
    body: [
      { text: "Sunrun's " },
      { text: "Sr. Program Manager, Grid Services", bold: true },
      { text: " scores 62 against her Data Program Management track, and it's remote. That's the one we'll tailor for." },
    ],
  },
  {
    c: 2, img: "05", url: "/jobs/sunrun-sr-program-manager", x: 1082, y: 158, zoom: 1.3, at: [0.38, 0.09],
    title: "One click to tailor",
    body: [
      { text: "Pick the track and hit " },
      { text: "Tailor", bold: true },
      { text: ". This demo uses the free trial, so no AI key is needed." },
    ],
  },
  {
    c: 2, img: "06", url: "/jobs/sunrun-sr-program-manager", x: 845, y: 196, zoom: 1.45, at: [0.23, 0.15],
    title: "What happens inside the run",
    body: [
      { text: "Rhapto reads the posting, " },
      { text: "selects", bold: true },
      { text: " the blocks that fit, has the AI " },
      { text: "compose", bold: true },
      { text: " a resume from them, then " },
      { text: "validates", bold: true },
      { text: " every line. A failed check gets one repair pass." },
    ],
  },
  {
    c: 2, img: "07", url: "/jobs/sunrun-sr-program-manager", x: 400, y: 450, zoom: 1.2, at: [0.32, 0.44],
    title: "It read the job properly",
    body: [
      { text: "About a minute later: the posting broken into " },
      { text: "must-haves", bold: true },
      { text: ", nice-to-haves and seniority, and a draft resume ready to review." },
    ],
  },
  {
    c: 3, img: "08", url: "/jobs/…/packages/v1", x: 797, y: 558, zoom: 1.3, at: [0.04, 0.42],
    title: "Every line shows its source",
    body: [
      { text: "The job on the left, her resume on the right. Under each line: the " },
      { text: "block it came from", bold: true },
      { text: ", and that it's verified. The run cost 13¢." },
    ],
  },
  {
    c: 3, img: "09", url: "/jobs/…/packages/v1", x: 935, y: 417, zoom: 1.35, at: [0.04, 0.42],
    title: "Tailored, not invented",
    body: [
      { text: "The wording is angled toward the job (delivery, governance, operations), but each claim, like " },
      { text: "35% less ticket triage time", bold: true },
      { text: ", comes from a verified block." },
    ],
  },
  {
    c: 3, img: "10", url: "/jobs/…/packages/v1", x: 970, y: 445, zoom: 1.35, at: [0.04, 0.42],
    title: "Click a line to see its receipt",
    body: [
      { text: "Here's the block behind that bullet: " },
      { text: "northwind-triage", bold: true },
      { text: ", verified, with the exact metric Maya confirmed." },
    ],
  },
  {
    c: 3, img: "11", url: "/jobs/…/packages/v1", x: 1219, y: 406, zoom: 1.4, at: [0.04, 0.42],
    title: "The checks ran, and passed",
    body: [
      { text: "Six checks ran on the draft, including source and number checks that can't be switched off. And the unverified " },
      { text: "42%", bold: true },
      { text: "? It isn't in the resume." },
    ],
  },
  {
    c: 3, img: "12", url: "/jobs/…/packages/v1", x: 960, y: 508, zoom: 1.35, at: [0.04, 0.42],
    title: "It names gaps instead of hiding them",
    body: [
      { text: "Maya hasn't worked in energy markets. The cover note says so plainly: " },
      { text: "“I have not yet worked inside DER or VPP markets.”", bold: true },
      { text: " It didn't invent experience to fit." },
    ],
  },
  {
    c: 4, img: "13", url: "/jobs/…/packages/v1", x: 960, y: 259, zoom: 1.35, at: [0.31, 0.21],
    title: "You apply, not a bot",
    body: [
      { text: "Download the PDF or Word file and apply on the employer's own site. Rhapto never submits anything; " },
      { text: "Mark applied", bold: true },
      { text: " just records it." },
    ],
  },
  {
    c: 4, img: "14", url: "/pipeline", x: 347, y: 341, zoom: 1.2, at: [0.29, 0.3],
    title: "Track what happens next",
    body: [
      {
        text: "Every application sits in her pipeline, with status, a follow-up date, notes and a link back to the exact resume she sent.",
      },
    ],
  },
];

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

/** Zoom toward the hotspot, clamped so the picture always fills the frame.
 *
 * All in fractions of the frame, which is why no measuring is needed: at a fixed aspect ratio the
 * screenshot-pixel maths divides out (tx / frameWidth and ty / frameHeight do not depend on the
 * rendered width). Same formula as the original tour, expressed once as percentages. With `zoom`
 * of 1 (reduced motion) it returns no shift, and the hotspot sits at its plain screenshot position. */
export function layout(x: number, y: number, zoom: number) {
  const fx = x / TOUR_W;
  const fy = y / TOUR_H;
  const tx = clamp(fx * (1 - zoom) + (0.5 - fx) * 0.35 * (zoom - 1), 1 - zoom, 0);
  const ty = clamp(fy * (1 - zoom) + (0.5 - fy) * 0.35 * (zoom - 1), 1 - zoom, 0);
  return {
    tx: tx * 100,
    ty: ty * 100,
    hx: (fx * zoom + tx) * 100,
    hy: (fy * zoom + ty) * 100,
  };
}

export const STEPS: readonly TourStep[] = RAW.map((s) => ({ ...s, ...layout(s.x, s.y, s.zoom) }));

/** Same steps with no zoom, for visitors who asked the OS for less motion. */
export const STEPS_STILL: readonly TourStep[] = RAW.map((s) => ({ ...s, ...layout(s.x, s.y, 1) }));

export const CHAPTER_FIRST_STEP: readonly number[] = CHAPTERS.map((_, k) => STEPS.findIndex((s) => s.c === k));
