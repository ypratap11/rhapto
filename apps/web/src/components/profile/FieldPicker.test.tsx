import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { FieldPicker } from "./FieldPicker";

const putTrack = vi.fn().mockResolvedValue({});
const onOpenChange = vi.fn();

// One entry per matched role — the real shape of GET /api/v1/taxonomy/suggestions
// (TaxonomySuggestionOut[]), not a wrapper object.
let suggestionsData: unknown[] = [{ field_id: "engineering", field_name: "Engineering", role_id: "backend", role_name: "Backend", matched_title: "Backend Engineer" }];

vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  usePutTrack: () => ({ mutateAsync: putTrack, isPending: false }),
  useBases: () => ({ data: [{ id: "default", name: "Default" }] }),
  useTaxonomy: () => ({
    data: {
      fields: [
        { id: "engineering", name: "Engineering", roles: [{ id: "backend", name: "Backend", keywords: ["api", "services"] }] },
        { id: "design", name: "Design", roles: [{ id: "product-designer", name: "Product Designer", keywords: ["figma"] }] },
      ],
    },
    isLoading: false,
    error: null,
    isPaused: false,
  }),
  useTaxonomySuggestions: () => ({ data: suggestionsData, isLoading: false, error: null, isPaused: false }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

describe("FieldPicker", () => {
  it("shows the fields, the roles of the chosen field, and creates a track at min_fit 60", async () => {
    const user = userEvent.setup({ delay: null });
    render(<FieldPicker open onOpenChange={onOpenChange} />);

    await user.click(screen.getByRole("button", { name: "Design" }));
    expect(screen.getByRole("button", { name: "Product Designer" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Engineering" }));
    // "Backend" is already offered as a one-tap suggestion chip up top, so the roles column does
    // not repeat it — one actionable button per role, not two.
    await user.click(screen.getByRole("button", { name: "Backend" }));
    expect(putTrack).toHaveBeenCalledWith(expect.objectContaining({ id: "backend", min_fit: 60, keywords: ["api", "services"], field: "engineering", role: "backend" }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("puts the resume's suggestions at the top as one-tap chips", async () => {
    const user = userEvent.setup({ delay: null });
    render(<FieldPicker open onOpenChange={vi.fn()} />);
    const group = screen.getByRole("group", { name: /suggested from your resume/i });
    await user.click(within(group).getByRole("button", { name: "Backend" }));
    expect(putTrack).toHaveBeenCalledWith(expect.objectContaining({ id: "backend" }));
  });

  it("defaults to the first field and shows no suggestion group when there are no suggestions", () => {
    suggestionsData = [];
    render(<FieldPicker open onOpenChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Engineering" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Backend" })).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: /suggested from your resume/i })).not.toBeInTheDocument();
    suggestionsData = [{ field_id: "engineering", field_name: "Engineering", role_id: "backend", role_name: "Backend", matched_title: "Backend Engineer" }];
  });
});
