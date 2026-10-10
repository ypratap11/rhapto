// The one place the contrast pair list and the globals.css parser live. Consumed by the vitest test
// (so `pnpm test`, which CI runs, enforces it) and by scripts/check-contrast.mjs (a thin CLI).
// Plain .mjs on purpose: Node 22.16 runs it directly from the CLI, and vitest/TS (allowJs) import it too.
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const CSS_PATH = resolve(dirname(fileURLToPath(import.meta.url)), "../../app/globals.css");
export const THRESHOLD = { text: 4.5, ui: 3 };

export function readCss() {
  return readFileSync(CSS_PATH, "utf8");
}

const BANDS = ["band-peach", "band-mint", "band-sand"];
const GLOWS = ["glow-from", "glow-mid"];
const ON_TINT = ["background", "surface", "surface-muted", ...BANDS, ...GLOWS];

/** @typedef {{ fg: string, bg: string, label: string, kind: "text" | "ui", mix?: { token: string, alpha: number } }} Pair */

/** @param {string} fg @param {string} bg @param {string} label @param {Pair["mix"]=} mix @returns {Pair} */
const text = (fg, bg, label, mix) => ({ fg, bg, label, kind: "text", ...(mix ? { mix } : {}) });

/** @type {Pair[]} */
export const PAIRS = [
  text("foreground", "background", "body text on page"),
  text("foreground", "surface", "body text on a card"),
  text("foreground", "surface-muted", "body text on a muted panel"),
  text("muted-foreground", "background", "muted text on page"),
  text("muted-foreground", "surface", "muted text on a card"),
  text("muted-foreground", "surface-muted", "muted text on a muted panel"),
  text("primary-foreground", "primary", "primary button label"),
  text("primary-foreground", "primary-hover", "primary button label (hover)"),
  text("destructive", "background", "destructive text on page"),
  text("fit-high", "fit-high-bg", "fit high chip"),
  text("fit-high", "surface", "fit high text on a card"),
  text("fit-mid", "fit-mid-bg", "fit mid chip"),
  text("fit-low", "fit-low-bg", "fit low chip"),
  text("diff-add", "diff-add-bg", "diff added word"),
  text("diff-del", "diff-del-bg", "diff removed word"),
  ...BANDS.map((b) => text("foreground", b, `headline on ${b}`)),
  ...GLOWS.map((b) => text("foreground", b, `headline on ${b}`)),
  // primary as TEXT (links, chips) on every surface it is painted on.
  ...ON_TINT.map((b) => text("primary", b, `primary text on ${b}`)),
  text("primary", "surface", "primary chip (10% primary over a card)", { token: "primary", alpha: 0.1 }),
  text("primary", "background", "primary chip (10% primary over the page)", { token: "primary", alpha: 0.1 }),
  // links on a band or glow are TEXT (4.5), not UI (3).
  ...[...BANDS, ...GLOWS].map((b) => text("link-on-band", b, `link on ${b}`)),
  ...[...BANDS, ...GLOWS].map((b) => text("muted-foreground", b, `muted text on ${b}`)),
  text("step-1-fg", "step-1", "step 1 numeral"),
  text("step-2-fg", "step-2", "step 2 numeral"),
  text("step-3-fg", "step-3", "step 3 numeral"),
  { fg: "ring", bg: "background", label: "focus ring on page", kind: "ui" },
  { fg: "ring", bg: "surface", label: "focus ring on a card", kind: "ui" },
];

const VALUE = /^\s*--([a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,8}|var\(--[a-z0-9-]+\))\s*;/;

/** Pull the custom properties out of one top-level rule (`:root` or `.dark`). */
function readBlock(css, selector) {
  const start = css.search(new RegExp(`^${selector}\\s*\\{`, "m"));
  if (start === -1) throw new Error(`No "${selector}" block in globals.css`);
  const end = css.indexOf("\n}", start);
  if (end === -1) throw new Error(`Unterminated "${selector}" block in globals.css`);
  /** @type {Record<string, string>} */
  const raw = {};
  for (const line of css.slice(start, end).split("\n")) {
    const m = VALUE.exec(line);
    if (m) raw[m[1]] = m[2];
  }
  /** @type {Record<string, string>} */
  const tokens = {};
  for (const [name, value] of Object.entries(raw)) {
    const ref = /^var\(--([a-z0-9-]+)\)$/.exec(value);
    if (!ref) {
      tokens[name] = value;
      continue;
    }
    const target = raw[ref[1]];
    if (target && target.startsWith("#")) tokens[name] = target; // one hop is all the file uses
  }
  return tokens;
}

/** @param {string} css @returns {{ light: Record<string, string>, dark: Record<string, string> }} */
export function parseThemes(css) {
  return { light: readBlock(css, ":root"), dark: readBlock(css, "\\.dark") };
}

function toRgb(hex) {
  let h = hex.slice(1);
  if (h.length === 3 || h.length === 4) h = [...h].map((c) => c + c).join("");
  if (h.length !== 6 && h.length !== 8) throw new Error(`Unsupported colour "${hex}"`);
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
}

/** `top` at `alpha` composited over opaque `bottom`, as a hex string. */
export function mixHex(top, alpha, bottom) {
  const t = toRgb(top);
  const b = toRgb(bottom);
  return "#" + t.map((v, i) => Math.round(v * alpha + b[i] * (1 - alpha)).toString(16).padStart(2, "0")).join("");
}

function relativeLuminance(hex) {
  const [r, g, b] = toRgb(hex)
    .map((c) => c / 255)
    .map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrast(fg, bg) {
  const a = relativeLuminance(fg);
  const b = relativeLuminance(bg);
  const [hi, lo] = a > b ? [a, b] : [b, a];
  return (hi + 0.05) / (lo + 0.05);
}

/** @typedef {{ theme: string, pair: Pair, fg: string, bg: string, ratio: number, required: number, pass: boolean }} Row */
/** @param {string} css @returns {{ rows: Row[], missing: string[] }} */
export function evaluate(css) {
  const themes = parseThemes(css);
  /** @type {Row[]} */
  const rows = [];
  /** @type {string[]} */
  const missing = [];
  for (const [theme, tokens] of Object.entries(themes)) {
    for (const pair of PAIRS) {
      const fg = tokens[pair.fg];
      let bg = tokens[pair.bg];
      const mixTop = pair.mix ? tokens[pair.mix.token] : undefined;
      if (!fg || !bg || (pair.mix && !mixTop)) {
        missing.push(`${theme}: --${pair.fg} / --${pair.bg}`);
        continue;
      }
      if (pair.mix && mixTop) bg = mixHex(mixTop, pair.mix.alpha, bg);
      const ratio = contrast(fg, bg);
      const required = THRESHOLD[pair.kind];
      rows.push({ theme, pair, fg, bg, ratio, required, pass: ratio >= required });
    }
  }
  return { rows, missing };
}
