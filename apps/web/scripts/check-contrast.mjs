#!/usr/bin/env node
// Reads the theme tokens out of src/app/globals.css and checks the pairs the design actually paints
// on top of each other against WCAG AA: 4.5:1 for text, 3:1 for UI boundaries and focus rings.
// Exits 1 if any pair falls short, so it can run in CI or before a commit.
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const CSS_PATH = resolve(dirname(fileURLToPath(import.meta.url)), "../src/app/globals.css");

/** @type {{ fg: string, bg: string, label: string, kind: "text" | "ui" }[]} */
const PAIRS = [
  { fg: "foreground", bg: "background", label: "body text on page", kind: "text" },
  { fg: "foreground", bg: "surface", label: "body text on a card", kind: "text" },
  { fg: "foreground", bg: "surface-muted", label: "body text on a muted panel", kind: "text" },
  { fg: "muted-foreground", bg: "background", label: "muted text on page", kind: "text" },
  { fg: "muted-foreground", bg: "surface", label: "muted text on a card", kind: "text" },
  { fg: "muted-foreground", bg: "surface-muted", label: "muted text on a muted panel", kind: "text" },
  { fg: "primary-foreground", bg: "primary", label: "primary button label", kind: "text" },
  { fg: "primary-foreground", bg: "primary-hover", label: "primary button label (hover)", kind: "text" },
  { fg: "destructive", bg: "background", label: "destructive text on page", kind: "text" },
  { fg: "fit-high", bg: "fit-high-bg", label: "fit high chip", kind: "text" },
  { fg: "fit-mid", bg: "fit-mid-bg", label: "fit mid chip", kind: "text" },
  { fg: "fit-low", bg: "fit-low-bg", label: "fit low chip", kind: "text" },
  { fg: "diff-add", bg: "diff-add-bg", label: "diff added word", kind: "text" },
  { fg: "diff-del", bg: "diff-del-bg", label: "diff removed word", kind: "text" },
  { fg: "primary", bg: "background", label: "primary surface on page", kind: "ui" },
  { fg: "primary", bg: "surface", label: "primary surface on a card", kind: "ui" },
  { fg: "ring", bg: "background", label: "focus ring on page", kind: "ui" },
  { fg: "ring", bg: "surface", label: "focus ring on a card", kind: "ui" },
  { fg: "foreground", bg: "band-peach", label: "hero headline on peach", kind: "text" },
  { fg: "foreground", bg: "band-mint", label: "hero headline on mint", kind: "text" },
  { fg: "foreground", bg: "band-sand", label: "hero headline on sand", kind: "text" },
  { fg: "muted-foreground", bg: "band-peach", label: "hero subtext on peach", kind: "text" },
  { fg: "muted-foreground", bg: "band-mint", label: "hero subtext on mint", kind: "text" },
  { fg: "muted-foreground", bg: "band-sand", label: "hero subtext on sand", kind: "text" },
  { fg: "primary", bg: "band-peach", label: "primary on peach", kind: "ui" },
  { fg: "primary", bg: "band-mint", label: "primary on mint", kind: "ui" },
  { fg: "primary", bg: "band-sand", label: "primary on sand", kind: "ui" },
];

const THRESHOLD = { text: 4.5, ui: 3 };

/** Pull the custom properties out of one top-level rule (`:root` or `.dark`). */
function readBlock(css, selector) {
  const start = css.search(new RegExp(`^${selector}\\s*\\{`, "m"));
  if (start === -1) throw new Error(`No "${selector}" block in ${CSS_PATH}`);
  const end = css.indexOf("}", start);
  if (end === -1) throw new Error(`Unterminated "${selector}" block in ${CSS_PATH}`);
  const tokens = {};
  for (const line of css.slice(start, end).split("\n")) {
    const match = /^\s*--([a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,8})\s*;/.exec(line);
    if (match) tokens[match[1]] = match[2];
  }
  return tokens;
}

function toRgb(hex) {
  let h = hex.slice(1);
  if (h.length === 3 || h.length === 4) h = [...h].map((c) => c + c).join("");
  if (h.length !== 6 && h.length !== 8) throw new Error(`Unsupported colour "${hex}"`);
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255);
}

function relativeLuminance(hex) {
  const [r, g, b] = toRgb(hex).map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(fg, bg) {
  const a = relativeLuminance(fg);
  const b = relativeLuminance(bg);
  const [hi, lo] = a > b ? [a, b] : [b, a];
  return (hi + 0.05) / (lo + 0.05);
}

const css = readFileSync(CSS_PATH, "utf8");
const themes = { light: readBlock(css, ":root"), dark: readBlock(css, "\\.dark") };

const rows = [];
const missing = [];
for (const [theme, tokens] of Object.entries(themes)) {
  for (const pair of PAIRS) {
    const fg = tokens[pair.fg];
    const bg = tokens[pair.bg];
    if (!fg || !bg) {
      missing.push(`${theme}: --${pair.fg} / --${pair.bg}`);
      continue;
    }
    const ratio = contrast(fg, bg);
    const required = THRESHOLD[pair.kind];
    rows.push({ theme, pair, fg, bg, ratio, required, pass: ratio >= required });
  }
}

const width = Math.max(...rows.map((r) => r.pair.label.length));
let failures = 0;
for (const theme of Object.keys(themes)) {
  console.log(`\n${theme}`);
  for (const row of rows.filter((r) => r.theme === theme)) {
    if (!row.pass) failures += 1;
    const mark = row.pass ? "PASS" : "FAIL";
    const tokenPair = `--${row.pair.fg} on --${row.pair.bg}`;
    console.log(
      `  ${mark}  ${row.pair.label.padEnd(width)}  ${row.ratio.toFixed(2).padStart(5)}:1 (needs ${row.required})  ${tokenPair} = ${row.fg} on ${row.bg}`,
    );
  }
}

if (missing.length > 0) {
  console.error(`\nMissing tokens:\n  ${missing.join("\n  ")}`);
}

if (failures > 0 || missing.length > 0) {
  console.error(`\n${failures} pair(s) below WCAG AA, ${missing.length} missing.`);
  process.exit(1);
}

console.log(`\nAll ${rows.length} pairs meet WCAG AA.`);

// Raw Tailwind palette classes bypass the tokens above, so nothing this script measures would
// catch them. globals.css is the one place a literal colour is allowed (spec §8).
import { readdirSync, statSync } from "node:fs";

const SRC = resolve(dirname(fileURLToPath(import.meta.url)), "../src");
const PALETTE = /(bg|text|border)-(red|amber|green|zinc|slate|indigo|emerald|yellow|blue|gray|neutral|stone)-\d+/g;

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const full = resolve(dir, name);
    return statSync(full).isDirectory() ? walk(full) : [full];
  });
}

const offenders = [];
for (const file of walk(SRC)) {
  if (!/\.(tsx?|css)$/.test(file) || file.endsWith("globals.css")) continue;
  for (const match of readFileSync(file, "utf8").matchAll(PALETTE)) {
    offenders.push(`${file.slice(SRC.length + 1)}: ${match[0]}`);
  }
}
if (offenders.length > 0) {
  console.error(`\nRaw palette classes outside globals.css:\n  ${offenders.join("\n  ")}`);
  process.exit(1);
}
console.log(`No raw palette classes under src/.`);
