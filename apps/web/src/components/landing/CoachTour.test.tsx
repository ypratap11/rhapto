import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as copy from "@/lib/coach/copy";
import { matchLabel } from "@/lib/coach/labels";
import { ACCESS_REQUEST_MAILTO, ACCESS_REQUEST_URL } from "./access";
import { CoachTour } from "./CoachTour";
import { primaryCta } from "./cta";
import { TOUR_CHANGES, TOUR_FILE, TOUR_JOBS, TOUR_ROLE } from "./coachTourData";

const flag = { value: true };
vi.mock("@/lib/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/client")>();
  return {
    ...actual,
    get SAME_ORIGIN_DEPLOYMENT() {
      return flag.value;
    },
  };
});
afterEach(() => {
  flag.value = true;
});

const panels = () => screen.getAllByRole("tabpanel", { hidden: true });
const INTERACTIVE = "a, button, input, select, textarea, [role='button'], [tabindex]:not([tabindex='-1'])";
const interactiveIn = (el: Element) => el.querySelector(INTERACTIVE);

describe("CoachTour", () => {
  it("has four tabs, the first selected, and all four panels in the DOM", () => {
    render(<CoachTour />);
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((t) => t.textContent)).toEqual(["1 Upload", "2 Role", "3 Top matches", "4 Your resume"]);
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
    expect(panels()).toHaveLength(4); // server-rendered: inactive panels are hidden, not absent
    expect(screen.getByRole("heading", { level: 2, name: "See the coach, step by step" })).toBeInTheDocument();
  });

  it("each panel carries a visible keyboard focus ring (the shared TabsContent removes the outline)", () => {
    render(<CoachTour />);
    for (const panel of panels()) expect(panel.className).toContain("focus-visible:ring");
  });

  it("is a section with the #tour anchor and room under the sticky bar", () => {
    const { container } = render(<CoachTour />);
    const section = container.querySelector("section#tour")!;
    expect(section.className).toContain("scroll-mt-20");
    expect(section).toHaveAttribute("aria-labelledby");
  });

  it("wraps the tab list instead of overflowing at 320px (Review Focus)", () => {
    render(<CoachTour />);
    const cls = screen.getByRole("tablist").className;
    expect(cls).toContain("flex-wrap");
    expect(cls).toContain("group-data-horizontal/tabs:h-auto");
  });

  it("moves selection by click and by arrow keys, wrapping, Home and End", async () => {
    const user = userEvent.setup();
    render(<CoachTour />);
    const tabs = () => screen.getAllByRole("tab");
    await user.click(tabs()[2]!);
    expect(tabs()[2]).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{ArrowRight}");
    expect(tabs()[3]).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{ArrowRight}");
    expect(tabs()[0]).toHaveAttribute("aria-selected", "true"); // wraps
    await user.keyboard("{ArrowLeft}");
    expect(tabs()[3]).toHaveAttribute("aria-selected", "true"); // wraps back
    await user.keyboard("{Home}");
    expect(tabs()[0]).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{End}");
    expect(tabs()[3]).toHaveAttribute("aria-selected", "true");
  });

  it("always shows the fictional-data line", async () => {
    const user = userEvent.setup();
    render(<CoachTour />);
    expect(screen.getByText("Example with a fictional person, Maya Chen.")).toBeInTheDocument();
    await user.click(screen.getAllByRole("tab")[3]!);
    expect(screen.getByText("Example with a fictional person, Maya Chen.")).toBeInTheDocument();
  });

  it("shows no interactive element inside any panel", () => {
    render(<CoachTour />);
    for (const panel of panels()) expect(interactiveIn(panel)).toBeNull();
  });

  it("the inert-panel check FAILS on a fixture panel containing a link", () => {
    render(<div role="tabpanel"><a href="/x">x</a></div>);
    expect(interactiveIn(screen.getByRole("tabpanel"))).not.toBeNull(); // same helper as the real check, so it proves that check can fail
  });

  it("the interactive elements of the window are the four tabs and the CTA links only", () => {
    const { container } = render(<CoachTour />);
    const outside = [...container.querySelectorAll("a, button")].filter((el) => el.getAttribute("role") !== "tab");
    expect(outside.length).toBeGreaterThan(0);
    for (const el of outside) expect(el.closest("[role='tabpanel']")).toBeNull();
  });

  it("panels show only coach strings from lib/coach/copy plus the fictional data (drift guard)", () => {
    render(<CoachTour />);
    const fictional = [
      TOUR_FILE,
      TOUR_ROLE,
      ...TOUR_JOBS.flatMap((j) => [j.title, j.company, matchLabel(j.fit, j.minFit)]),
      ...TOUR_CHANGES.flatMap((c) => [c.reason, c.after]),
    ];
    const known = [
      copy.UPLOAD_TITLE, copy.UPLOAD_HINT, copy.CHOOSE_FILE,
      copy.roleQuestion(TOUR_ROLE), copy.ROLE_YES, copy.ROLE_OTHER,
      copy.matchesTitle(TOUR_ROLE), copy.TAILOR_THIS,
      copy.RESULT_TITLE, copy.RESULT_READY, copy.DOWNLOAD_DOCX, copy.DOWNLOAD_PDF, copy.WHAT_CHANGED,
    ];
    for (const panel of panels()) {
      let left = panel.textContent ?? "";
      for (const s of [...known, ...fictional].sort((a, b) => b.length - a.length)) left = left.split(s).join("");
      expect(left.trim(), "text in a panel that the coach does not show").toBe("");
    }
    // and nothing from the old invented copy
    expect(document.body.textContent).not.toMatch(/Read 3 roles|We think you are aiming/);
  });

  it("panel 1 is title, hint and the file chip only: no transcript line", () => {
    render(<CoachTour />);
    const first = panels()[0]!;
    expect(first.textContent).toContain(copy.UPLOAD_TITLE);
    expect(first.textContent).toContain(copy.UPLOAD_HINT);
    expect(first.textContent).toContain("maya-chen-resume.docx");
    expect(first.textContent).not.toMatch(/Resume:/);
  });

  it("draws match labels as the coach does: Strong, Strong, Good, with the three fictional companies", () => {
    render(<CoachTour />);
    const third = panels()[2]!;
    expect(within(third).getAllByText("Strong match")).toHaveLength(2);
    expect(within(third).getAllByText("Good match")).toHaveLength(1);
    for (const c of ["Contoso Robotics", "Fabrikam Health", "Tailspin Air"]) expect(third.textContent).toContain(c);
  });

  it("hosted: 'Try it with your resume' matches the primary CTA, and the request-access link is beside it", () => {
    render(<CoachTour />);
    const cta = screen.getByRole("link", { name: /Try it with your resume/ });
    expect(cta).toHaveAttribute("href", primaryCta(true).href);
    const request = screen.getByRole("link", { name: "Request beta access" });
    expect(request).toHaveAttribute("href", ACCESS_REQUEST_URL || ACCESS_REQUEST_MAILTO);
    expect(screen.getByText(/No invite yet\?/)).toBeInTheDocument();
  });

  it("token mode: goes to /settings and shows neither /start nor a request link", () => {
    flag.value = false;
    const { container } = render(<CoachTour />);
    expect(screen.getByRole("link", { name: /Try it with your resume/ })).toHaveAttribute("href", "/settings");
    expect(screen.queryByRole("link", { name: /request beta access/i })).toBeNull();
    expect(container.querySelector("a[href='/start']")).toBeNull();
  });
});
