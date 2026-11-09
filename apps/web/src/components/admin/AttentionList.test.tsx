import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AttentionList } from "./AttentionList";

describe("AttentionList", () => {
  it("says so when the list is empty", () => {
    render(<AttentionList alerts={[]} />);
    expect(screen.getByText("Nothing needs your attention")).toBeTruthy();
  });
  it("renders each alert title and detail", () => {
    render(
      <AttentionList
        alerts={[
          { id: "a", tone: "warn", title: "Budget soon", detail: "Runs out on 21 Nov" },
          { id: "b", tone: "info", title: "Ready to ask", detail: "7 people" },
        ]}
      />,
    );
    expect(screen.getByText("Budget soon")).toBeTruthy();
    expect(screen.getByText("Runs out on 21 Nov")).toBeTruthy();
    expect(screen.getByText("Ready to ask")).toBeTruthy();
    expect(screen.getByText("7 people")).toBeTruthy();
  });
  it("warn and info dots use different token classes", () => {
    render(
      <AttentionList
        alerts={[
          { id: "a", tone: "warn", title: "W", detail: "d" },
          { id: "b", tone: "info", title: "I", detail: "d" },
        ]}
      />,
    );
    const warn = screen.getByTestId("dot-a").className;
    const info = screen.getByTestId("dot-b").className;
    expect(warn).toContain("bg-fit-mid");
    expect(info).toContain("bg-fit-high");
    expect(warn).not.toBe(info);
  });
});
