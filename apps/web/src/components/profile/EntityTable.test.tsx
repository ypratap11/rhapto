import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { EntityTable } from "./EntityTable";

type Row = { id: string; name: string; detail: string };
const rows: Row[] = [
  { id: "a", name: "A very long employer name that would not fit a narrow sheet · Senior Staff Program Manager", detail: "not confirmed yet" },
  { id: "b", name: "Second", detail: "confirmed" },
];

function renderTable() {
  return render(
    <EntityTable<Row>
      rows={rows}
      getKey={(r) => r.id}
      getLabel={(r) => r.id}
      onEdit={vi.fn()}
      onDelete={vi.fn()}
      emptyText="none"
      columns={[
        { key: "name", header: "Name", render: (r) => r.name },
        { key: "detail", header: "State", render: (r) => r.detail },
      ]}
    />,
  );
}

describe("EntityTable layout", () => {
  it("is a wrapping card list, so it never needs a sideways scroller", () => {
    const { container } = renderTable();
    // A <table> of nowrap cells is what overflowed the ~520px sheet and the 375px phone.
    expect(container.querySelector("table")).toBeNull();
    expect(container.querySelector("[data-slot=table-container]")).toBeNull();
    // The row's content area (the action buttons carry their own nowrap, which is fine) must wrap.
    for (const content of container.querySelectorAll("[data-slot=entity-row] > div:first-child")) {
      expect(content.innerHTML).not.toMatch(/whitespace-nowrap|overflow-x|overflow-auto|table-cell/);
    }
    expect(container.querySelectorAll("[data-slot=entity-row]")).toHaveLength(2);
  });

  it("keeps Edit and Delete in every row, outside the shrinkable content", () => {
    renderTable();
    for (const row of document.querySelectorAll<HTMLElement>("[data-slot=entity-row]")) {
      const r = within(row);
      const edit = r.getByRole("button", { name: /^edit/i });
      expect(edit.parentElement!.className).toContain("shrink-0");
      expect(r.getByRole("button", { name: /^delete/i })).toBeInTheDocument();
    }
    expect(screen.getAllByText("State")).toHaveLength(2);
  });

  it("lets a label and its value wrap onto two lines instead of squeezing the label", () => {
    renderTable();
    // A wide value (the "not confirmed yet" button) once squeezed its label to "Confir" at 375px.
    for (const label of screen.getAllByText("State")) {
      expect(label.className).toContain("shrink-0");
      expect(label.parentElement!.className).toContain("flex-wrap");
    }
  });
});
