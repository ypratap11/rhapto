import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FieldPicker } from "./FieldPicker";

const putTrack = vi.fn().mockResolvedValue({});
const onOpenChange = vi.fn();

type QueryState<T> = { data: T | undefined; isLoading: boolean; error: unknown; isPaused: boolean };
function ok<T>(data: T): QueryState<T> {
  return { data, isLoading: false, error: null, isPaused: false };
}

const defaultTaxonomy = {
  fields: [
    { id: "engineering", name: "Engineering", roles: [{ id: "backend", name: "Backend", keywords: ["api", "services"] }] },
    { id: "design", name: "Design", roles: [{ id: "product-designer", name: "Product Designer", keywords: ["figma"] }] },
  ],
};
// The real shape of GET /api/v1/taxonomy/suggestions (TaxonomySuggestionOut[]) — a flat array, not
// a { roles: [...] } wrapper.
const defaultSuggestions = [{ field_id: "engineering", field_name: "Engineering", role_id: "backend", role_name: "Backend", matched_title: "Backend Engineer" }];

const state = {
  taxonomy: ok(defaultTaxonomy),
  suggestions: ok(defaultSuggestions),
};

vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  usePutTrack: () => ({ mutateAsync: putTrack, isPending: false }),
  useBases: () => ({ data: [{ id: "default", name: "Default" }] }),
  useTaxonomy: () => state.taxonomy,
  useTaxonomySuggestions: () => state.suggestions,
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

describe("FieldPicker", () => {
  beforeEach(() => {
    state.taxonomy = ok(defaultTaxonomy);
    state.suggestions = ok(defaultSuggestions);
    putTrack.mockClear();
    onOpenChange.mockClear();
  });

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
    state.suggestions = ok([]);
    render(<FieldPicker open onOpenChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Engineering" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Backend" })).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: /suggested from your resume/i })).not.toBeInTheDocument();
  });

  describe("taxonomy's own loading/failed/stale states", () => {
    it("shows a skeleton while the taxonomy is loading, not an empty picker", () => {
      state.taxonomy = { data: undefined, isLoading: true, error: null, isPaused: false };
      render(<FieldPicker open onOpenChange={vi.fn()} />);
      expect(screen.queryByRole("button", { name: "Engineering" })).not.toBeInTheDocument();
      expect(document.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0);
    });

    it("shows an error banner instead of the picker when the taxonomy call fails with nothing cached", () => {
      state.taxonomy = { data: undefined, isLoading: false, error: new Error("boom"), isPaused: false };
      render(<FieldPicker open onOpenChange={vi.fn()} />);
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Engineering" })).not.toBeInTheDocument();
    });

    it("keeps the picker usable from cached data, with a banner, when a background refetch is paused", () => {
      state.taxonomy = { data: defaultTaxonomy, isLoading: false, error: null, isPaused: true };
      render(<FieldPicker open onOpenChange={vi.fn()} />);
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Engineering" })).toBeInTheDocument();
    });

    it("says so when the taxonomy genuinely has no fields", () => {
      state.taxonomy = ok({ fields: [] });
      render(<FieldPicker open onOpenChange={vi.fn()} />);
      expect(screen.getByText("No fields configured yet.")).toBeInTheDocument();
      expect(screen.queryByRole("group", { name: "Fields" })).not.toBeInTheDocument();
    });
  });

  describe("suggestions' own loading/failed/stale states", () => {
    it("shows a loading placeholder for suggestions, not the same empty look a no-match resume has", () => {
      state.suggestions = { data: undefined, isLoading: true, error: null, isPaused: false };
      render(<FieldPicker open onOpenChange={vi.fn()} />);
      expect(screen.queryByRole("group", { name: /suggested from your resume/i })).not.toBeInTheDocument();
      expect(screen.queryByText(/couldn.?t load suggestions/i)).not.toBeInTheDocument();
      expect(document.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0);
      // The rest of the picker (backed by the already-resolved taxonomy) stays usable while only
      // suggestions are still loading.
      expect(screen.getByRole("button", { name: "Engineering" })).toBeInTheDocument();
    });

    it("says suggestions failed to load, distinct from silently having none, when nothing is cached", () => {
      state.suggestions = { data: undefined, isLoading: false, error: new Error("boom"), isPaused: false };
      render(<FieldPicker open onOpenChange={vi.fn()} />);
      expect(screen.getByText(/couldn.?t load suggestions from your resume/i)).toBeInTheDocument();
      expect(screen.queryByRole("group", { name: /suggested from your resume/i })).not.toBeInTheDocument();
    });

    it("keeps cached suggestion chips visible, with a note, when a background refetch fails", () => {
      state.suggestions = { data: defaultSuggestions, isLoading: false, error: new Error("boom"), isPaused: false };
      render(<FieldPicker open onOpenChange={vi.fn()} />);
      const group = screen.getByRole("group", { name: /suggested from your resume/i });
      expect(within(group).getByRole("button", { name: "Backend" })).toBeInTheDocument();
      expect(within(group).getByText(/couldn.?t refresh/i)).toBeInTheDocument();
    });
  });
});
