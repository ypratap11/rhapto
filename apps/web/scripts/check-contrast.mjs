#!/usr/bin/env node
// Thin CLI over src/lib/contrast/contrast.mjs (the same module the vitest test uses).
// Exits 1 if any pair falls short, so it can run before a commit.
import { evaluate, readCss } from "../src/lib/contrast/contrast.mjs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { readFileSync } from "node:fs";

const { rows, missing } = evaluate(readCss());
const width = Math.max(...rows.map((r) => r.pair.label.length));
let failures = 0;
for (const theme of ["light", "dark"]) {
  console.log(`\n${theme}`);
  for (const row of rows.filter((r) => r.theme === theme)) {
    if (!row.pass) failures += 1;
    console.log(
      `  ${row.pass ? "PASS" : "FAIL"}  ${row.pair.label.padEnd(width)}  ${row.ratio.toFixed(2).padStart(5)}:1 (needs ${row.required})  --${row.pair.fg} on --${row.pair.bg} = ${row.fg} on ${row.bg}`,
    );
  }
}
if (missing.length > 0) console.error(`\nMissing tokens:\n  ${missing.join("\n  ")}`);
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
