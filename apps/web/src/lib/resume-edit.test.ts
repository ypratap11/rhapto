import { describe, expect, it } from "vitest";
import type { ResumeDocument } from "@/lib/api/queries";
import { isSameResume, removeBullet, updateBulletText } from "./resume-edit";

const resume: ResumeDocument = {
  header: { name: "Maya Chen", email: null, phone: null, location: null, links: [] },
  summary: [{ text: "Summary one.", source_block_id: "acme-data-pm" }],
  sections: [
    {
      title: "Experience",
      kind: "experience",
      entries: [
        {
          source_block_id: "acme-data-pm",
          org: "Acme Analytics",
          role: "Senior Data Program Manager",
          period: "2019-2025",
          title: null,
          bullets: [
            { text: "Led delivery.", source_block_id: "acme-data-pm" },
            { text: "Owned migration.", source_block_id: "acme-migration" },
          ],
        },
      ],
    },
  ],
};

describe("resume-edit", () => {
  it("updates bullet text immutably and keeps the source block", () => {
    const next = updateBulletText(resume, "sections[0].entries[0].bullets[1]", "Owned the Snowflake migration.");
    expect(next).not.toBe(resume);
    expect(next.sections[0]!.entries[0]!.bullets[1]).toEqual({ text: "Owned the Snowflake migration.", source_block_id: "acme-migration" });
    expect(resume.sections[0]!.entries[0]!.bullets[1]!.text).toBe("Owned migration.");
    expect(updateBulletText(resume, "summary[0]", "New summary.").summary[0]!.text).toBe("New summary.");
  });
  it("returns the same object for non-bullet paths", () => {
    expect(updateBulletText(resume, "sections[0].entries[0]", "x")).toBe(resume);
    expect(updateBulletText(resume, "cover_note", "x")).toBe(resume);
  });
  it("removes bullets and empty headerless entries", () => {
    const next = removeBullet(resume, "sections[0].entries[0].bullets[0]");
    expect(next.sections[0]!.entries[0]!.bullets).toHaveLength(1);
    const headerless: ResumeDocument = { ...resume, sections: [{ title: "Credentials", kind: "credentials", entries: [{ source_block_id: "cred-pmp", org: null, role: null, period: null, title: null, bullets: [{ text: "PMP.", source_block_id: "cred-pmp" }] }] }] };
    expect(removeBullet(headerless, "sections[0].entries[0].bullets[0]").sections[0]!.entries).toHaveLength(0);
  });
  it("compares resumes", () => {
    expect(isSameResume(resume, structuredClone(resume))).toBe(true);
    expect(isSameResume(resume, updateBulletText(resume, "summary[0]", "x"))).toBe(false);
  });
});
