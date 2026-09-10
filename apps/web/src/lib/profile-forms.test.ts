import { describe, expect, it } from "vitest";
import type { Block } from "@/lib/api/queries";
import { blockToForm, formToBlock, parseJsonObject, splitList, validateBlockForm } from "./profile-forms";

const block: Block = {
  id: "acme-migration",
  type: "achievement",
  org: "Acme Analytics",
  role: null,
  period: "2023",
  verified: true,
  metric: "Migrated 12 pipelines with zero downtime, cutting warehouse cost 18%",
  content: "Owned the Snowflake migration program end to end.",
  tags: ["migration", "cost"],
  attribution: null,
  concurrent: false,
  visibility: { exclude_when: ["agency"] },
};

describe("profile forms", () => {
  it("splits and de-duplicates lists", () => {
    expect(splitList("a, b\nc,,a ")).toEqual(["a", "b", "c"]);
    expect(splitList("")).toEqual([]);
  });
  it("round-trips a block through the form", () => {
    const form = blockToForm(block);
    expect(form.tags).toBe("migration, cost");
    expect(form.exclude_when).toBe("agency");
    expect(formToBlock(form)).toEqual(block);
  });
  it("drops empty optional fields and visibility", () => {
    const form = { ...blockToForm(block), org: "", metric: "", exclude_when: "", period: "" };
    const out = formToBlock(form);
    expect(out.org).toBeNull();
    expect(out.metric).toBeNull();
    expect(out.period).toBeNull();
    expect(out.visibility).toBeNull();
  });
  it("validates id, type, content, and period", () => {
    expect(validateBlockForm(blockToForm(block))).toEqual({});
    expect(validateBlockForm({ ...blockToForm(block), id: "Bad Id" })).toHaveProperty("id");
    expect(validateBlockForm({ ...blockToForm(block), content: "" })).toHaveProperty("content");
    expect(validateBlockForm({ ...blockToForm(block), period: "Spring 2020" })).toHaveProperty("period");
    expect(validateBlockForm({ ...blockToForm(block), period: "Mar 2019 – Present" })).toEqual({});
  });
  it("parses JSON objects for guardrail config", () => {
    expect(parseJsonObject("")).toEqual({ value: {}, error: null });
    expect(parseJsonObject('{"fuzzy_threshold": 85}')).toEqual({ value: { fuzzy_threshold: 85 }, error: null });
    expect(parseJsonObject("[1]").error).toMatch(/object/);
    expect(parseJsonObject("{").error).toMatch(/JSON/);
  });
});
