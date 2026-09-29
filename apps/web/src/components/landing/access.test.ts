import { describe, expect, it } from "vitest";
import {
  ACCESS_REQUEST_EMAIL,
  ACCESS_REQUEST_MAILTO,
  ACCESS_REQUEST_URL,
  accessRequestLink,
} from "./access";

describe("accessRequestLink", () => {
  it("ships pointing at the owner's Google Form, opened as an external link", () => {
    expect(ACCESS_REQUEST_URL).toBe("https://forms.gle/1GUeGcKB9fCiJAdFA");
    expect(accessRequestLink(ACCESS_REQUEST_URL)).toEqual({
      href: "https://forms.gle/1GUeGcKB9fCiJAdFA",
      external: true,
    });
    // No argument means the constant.
    expect(accessRequestLink()).toEqual(accessRequestLink(ACCESS_REQUEST_URL));
  });

  it("falls back to the mailto when the URL is empty, which is how it shipped before the form existed", () => {
    expect(accessRequestLink("")).toEqual({ href: ACCESS_REQUEST_MAILTO, external: false });
  });

  it("keeps the mailto spelled out, so a typo'd address cannot agree with itself", () => {
    expect(ACCESS_REQUEST_EMAIL).toBe("hellorhapto@augaster.com");
    expect(ACCESS_REQUEST_MAILTO).toBe(
      "mailto:hellorhapto@augaster.com?subject=Rhapto%20access%20request",
    );
  });

  it("uses an https URL as given and marks it external", () => {
    const url = "https://forms.gle/example123";
    expect(accessRequestLink(url)).toEqual({ href: url, external: true });
  });

  it.each([
    ["http", "http://forms.example.com/x"],
    ["javascript:", "javascript:alert(1)"],
    ["mailto", "mailto:someone@example.com"],
    ["not a URL", "forms.gle/no-scheme"],
    ["whitespace", "   "],
    ["empty", ""],
  ])("falls back to the mailto for %s", (_label, url) => {
    expect(accessRequestLink(url)).toEqual({ href: ACCESS_REQUEST_MAILTO, external: false });
  });
});
