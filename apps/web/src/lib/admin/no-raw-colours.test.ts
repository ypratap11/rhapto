import { mkdtempSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const BAD: Array<[string, RegExp]> = [
  ["hex colour", /#[0-9a-fA-F]{3,8}\b/],
  ["rgb()", /\brgba?\(/],
  ["hsl()", /\bhsla?\(/],
  ["inline colour style", /style=\{\{[^}]*(color|background)/i],
];

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    if (statSync(p).isDirectory()) return files(p);
    return /\.tsx?$/.test(n) && !/\.test\.tsx?$/.test(n) && n !== "test-utils.tsx" ? [p] : [];
  });
}
function offences(dir: string): string[] {
  return files(dir).flatMap((f) => {
    const text = readFileSync(f, "utf8");
    return BAD.filter(([, re]) => re.test(text)).map(([what]) => `${f}: ${what}`);
  });
}
const root = join(__dirname, "../..");

describe("admin UI uses theme tokens only", () => {
  it("has no raw colours", () => {
    expect(files(join(root, "components/admin")).length).toBeGreaterThan(3);
    expect(offences(join(root, "components/admin"))).toEqual([]);
    expect(offences(join(root, "app/admin"))).toEqual([]);
  });
  it("catches a file containing #fff", () => {
    const dir = mkdtempSync(join(tmpdir(), "rawcol-"));
    try {
      writeFileSync(join(dir, "bad.tsx"), 'export const x = <i className="a" style={{ color: "#fff" }} />;');
      expect(offences(dir).length).toBeGreaterThan(0);
    } finally {
      rmSync(dir, { recursive: true });
    }
  });
});
