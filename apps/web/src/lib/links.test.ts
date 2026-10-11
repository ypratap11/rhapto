import { describe, expect, it } from "vitest";
import { safeHttpUrl } from "./links";

describe("safeHttpUrl", () => {
  it("keeps http and https links", () => {
    expect(safeHttpUrl("https://jobs.example.com/a?b=1")).toBe("https://jobs.example.com/a?b=1");
    expect(safeHttpUrl("http://example.com/")).toBe("http://example.com/");
  });

  it.each(["javascript:alert(1)", "JavaScript:alert(1)", " javascript:alert(1)", "data:text/html,<script>1</script>", "vbscript:x", "file:///etc/passwd"])(
    "rejects %s",
    (raw) => {
      expect(safeHttpUrl(raw)).toBeNull();
    },
  );

  it("rejects relative, empty and malformed values", () => {
    expect(safeHttpUrl("/jobs/1")).toBeNull();
    expect(safeHttpUrl("")).toBeNull();
    expect(safeHttpUrl(null)).toBeNull();
    expect(safeHttpUrl(undefined)).toBeNull();
    expect(safeHttpUrl("not a url")).toBeNull();
  });
});
