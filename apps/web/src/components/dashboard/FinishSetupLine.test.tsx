import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import type { DashboardChecklist } from "@/lib/api/queries";
import { FinishSetupLine } from "./FinishSetupLine";

const done = { resume_template: true, tracks: true } as unknown as DashboardChecklist;
const checklist = (over: Partial<Record<"resume_template" | "tracks", boolean>>) => ({ ...done, ...over }) as unknown as DashboardChecklist;

beforeEach(() => window.localStorage.clear());

describe("FinishSetupLine", () => {
  it("renders nothing when the required items are done", () => {
    const { container } = render(<FinishSetupLine checklist={done} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing without a checklist", () => {
    const { container } = render(<FinishSetupLine checklist={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("says one thing is left and links to the profile", () => {
    render(<FinishSetupLine checklist={checklist({ tracks: false })} />);
    expect(screen.getByRole("link", { name: "1 thing to finish in your profile ›" })).toHaveAttribute("href", "/profile");
  });

  it("counts two", () => {
    render(<FinishSetupLine checklist={checklist({ tracks: false, resume_template: false })} />);
    expect(screen.getByRole("link", { name: "2 things to finish in your profile ›" })).toBeInTheDocument();
  });

  it("can be dismissed, and stays dismissed", async () => {
    const user = userEvent.setup({ delay: null });
    const { unmount } = render(<FinishSetupLine checklist={checklist({ tracks: false })} />);
    await user.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByRole("link")).toBeNull();
    unmount();
    const again = render(<FinishSetupLine checklist={checklist({ tracks: false })} />);
    expect(again.container).toBeEmptyDOMElement();
  });
});
