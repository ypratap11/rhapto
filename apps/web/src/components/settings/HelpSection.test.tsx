import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { HelpSection } from "./HelpSection";

describe("HelpSection", () => {
  it("calls the applications guide by what it is, keeping its file", () => {
    render(<HelpSection />);
    expect(screen.getByText("Tracking your applications")).toBeInTheDocument();
    expect(screen.getByText("docs/user-guide/pipeline.md")).toBeInTheDocument();
    expect(screen.queryByText(/your pipeline/i)).toBeNull();
  });
});
