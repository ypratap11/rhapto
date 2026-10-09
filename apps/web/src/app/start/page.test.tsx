import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import StartPage from "./page";

vi.mock("@/components/coach/Coach", () => ({ Coach: () => <div>coach</div> }));

describe("StartPage", () => {
  it("mounts the coach (inside a Suspense boundary, which useSearchParams needs)", () => {
    render(<StartPage />);
    expect(screen.getByText("coach")).toBeInTheDocument();
  });
});
