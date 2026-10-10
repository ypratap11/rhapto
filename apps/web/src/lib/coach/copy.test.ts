import { describe, expect, it } from "vitest";
import * as copy from "./copy";

describe("coach copy", () => {
  it("holds the exact strings the coach screens show", () => {
    expect(copy.UPLOAD_TITLE).toBe("Upload your resume");
    expect(copy.UPLOAD_HINT).toBe("A Word (.docx) file, up to 5 MB.");
    expect(copy.CHOOSE_FILE).toBe("Choose a file");
    expect(copy.roleQuestion("Data Program Manager")).toBe("Looks like you're aiming for: Data Program Manager. Right?");
    expect(copy.ROLE_YES).toBe("Yes, that's right");
    expect(copy.ROLE_OTHER).toBe("Something else");
    expect(copy.matchesTitle("Data Program Manager")).toBe("Your top matches for Data Program Manager");
    expect(copy.TAILOR_THIS).toBe("Tailor this one");
    expect(copy.RESULT_TITLE).toBe("Your tailored resume");
    expect(copy.RESULT_READY).toBe("Ready for you to read. Check it before you send it.");
    expect(copy.DOWNLOAD_DOCX).toBe("Download DOCX");
    expect(copy.DOWNLOAD_PDF).toBe("Download PDF");
    expect(copy.WHAT_CHANGED).toBe("What changed");
  });
});
