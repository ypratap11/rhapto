import { resolve } from "node:path";
import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures";

const FIXTURE_DOCX = resolve(__dirname, "fixtures/resume-template.docx");

function checklistRow(page: Page, label: string) {
  return page.getByRole("region", { name: /profile checklist/i }).getByRole("listitem").filter({ hasText: label });
}

test("the field picker creates a track, and its resume-suggestion chips only appear once a template is uploaded", async ({ page }) => {
  await page.goto("/profile?card=tracks");

  // Start from zero tracks so the checklist's Tracks row has something to flip: profile.example
  // ships with two (data-pm, ai-pm) already, so "done" is otherwise already true before this test
  // does anything.
  for (const trackId of ["data-pm", "ai-pm"]) {
    await page.getByRole("button", { name: `Delete ${trackId}` }).click();
    await page.getByRole("alertdialog").getByRole("button", { name: "Delete", exact: true }).click();
  }
  // The Tracks tab's own empty state ("No tracks yet. Import your profile or add a track.",
  // EntityTable's emptyText) — not the Profile page's card-summary line for Tracks, which starts
  // with the same words ("No tracks yet. Pick a field and a role.") and is visible at the same time.
  await expect(page.getByText("No tracks yet. Import your profile or add a track.")).toBeVisible();

  await page.goto("/dashboard");
  await expect(checklistRow(page, "Tracks")).toHaveAttribute("data-done", "false");

  // Remove the resume document (uploaded by an earlier setup step / prior run of this suite —
  // see global-setup.ts) so the "suggested from your resume" chips have nothing to suggest from.
  await page.goto("/profile?card=resume-template");
  // `.count()` below does not auto-wait — settle the resume-document fetch first, or a still-
  // loading card (which renders neither the doc's Delete button nor the upload prompt yet) reads
  // as "no document" and this whole block is silently skipped.
  await page.waitForLoadState("networkidle");
  const deleteDocButton = page.getByRole("button", { name: /^Delete /i });
  if (await deleteDocButton.count()) {
    await deleteDocButton.click();
    await page.getByRole("alertdialog").getByRole("button", { name: "Delete", exact: true }).click();
  }
  await expect(page.getByText("Upload your resume (.docx)")).toBeVisible();

  await page.goto("/profile?card=tracks");
  await page.getByRole("button", { name: "Pick a field and role" }).click();
  await expect(page.getByRole("group", { name: "Suggested from your resume" })).toHaveCount(0);
  await page.keyboard.press("Escape");

  // Upload the fictional fixture (the same "Maya Chen" document apps/api's own tests use — see
  // apps/api/tests/helpers_docx.py) via the resume-template card's file input.
  await page.goto("/profile?card=resume-template");
  await page.getByLabel("Resume document").setInputFiles(FIXTURE_DOCX);
  const resumeCard = page.getByRole("dialog", { name: "Resume template" });
  await expect(resumeCard.getByRole("heading", { name: "resume-template.docx" })).toBeVisible();
  // The name/contact lines (paragraph roles "name"/"contact") belong to no section and are never
  // rendered by ResumeDocumentTab; the summary line is, so it is the actual proof the upload was
  // parsed rather than just accepted.
  await expect(resumeCard.getByText("Senior Data Program Manager with 8 years")).toBeVisible();

  await page.goto("/profile?card=tracks");
  await page.getByRole("button", { name: "Pick a field and role" }).click();
  const suggestions = page.getByRole("group", { name: "Suggested from your resume" });
  await expect(suggestions).toBeVisible();
  const chips = suggestions.getByRole("button");
  await expect(chips.first()).toBeVisible();
  await chips.first().click();
  await expect(page.getByText(/^Added the .* track$/)).toBeVisible();

  await page.goto("/dashboard");
  await expect(checklistRow(page, "Tracks")).toHaveAttribute("data-done", "true");
});
