import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { JobOut } from "@/lib/api/queries";
import { SimilarPostings } from "./SimilarPostings";

const similar = vi.fn();
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useSimilarPostings: (ids: string[], enabled: boolean) => similar(ids, enabled),
}));

function copy(id: string, extra: Partial<JobOut> = {}): JobOut {
  return { id, title: "Senior Engineer", location: "Austin, TX", source: "themuse", ...extra } as unknown as JobOut;
}

beforeEach(() => {
  similar.mockReset();
  similar.mockReturnValue({ data: undefined, isLoading: false, isError: false });
});

describe("SimilarPostings", () => {
  it("shows the count and fetches nothing until it is opened", () => {
    render(<SimilarPostings ids={["a", "b", "c"]} />);
    expect(screen.getByRole("button", { name: "+3 similar postings" })).toBeInTheDocument();
    expect(similar).toHaveBeenLastCalledWith(["a", "b", "c"], false);
  });

  it("opens the copies, each linking to its own job page", async () => {
    const user = userEvent.setup({ delay: null });
    similar.mockReturnValue({ data: [copy("a"), copy("b", { location: null })], isLoading: false, isError: false });
    render(<SimilarPostings ids={["a", "b"]} />);
    await user.click(screen.getByRole("button", { name: "+2 similar postings" }));
    expect(similar).toHaveBeenLastCalledWith(["a", "b"], true);
    const links = screen.getAllByRole("link", { name: "Senior Engineer" });
    expect(links.map((l) => l.getAttribute("href"))).toEqual(["/jobs/a", "/jobs/b"]);
    expect(screen.getByText(/Location not listed/)).toBeInTheDocument();
  });

  it("says 1 similar posting for a single copy", () => {
    render(<SimilarPostings ids={["a"]} />);
    expect(screen.getByRole("button", { name: "+1 similar posting" })).toBeInTheDocument();
  });

  it("says so when the copies cannot be loaded", async () => {
    const user = userEvent.setup({ delay: null });
    similar.mockReturnValue({ data: undefined, isLoading: false, isError: true });
    render(<SimilarPostings ids={["a"]} />);
    await user.click(screen.getByRole("button", { name: "+1 similar posting" }));
    expect(screen.getByText(/couldn.t load the other postings/i)).toBeInTheDocument();
  });
});
