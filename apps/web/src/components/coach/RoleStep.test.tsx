import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/client";
import * as copy from "@/lib/coach/copy";
import { readConfirmedTrack, readProposal, writeProposal } from "@/lib/coach/storage";
import { RoleStep } from "./RoleStep";

const save = vi.fn();
const saver = { ready: true };
const fire = vi.fn<(step: string) => Promise<void>>(async () => undefined);
vi.mock("@/lib/coach/events", () => ({ fireCoachEvent: (step: string) => fire(step) }));
vi.mock("@/lib/coach/role", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/coach/role")>()),
  useSaveCoachRole: () => ({ ready: saver.ready, isSaving: false, save }),
}));
vi.mock("@/lib/api/queries", () => ({
  useTaxonomy: () => ({
    data: {
      fields: [
        {
          id: "program-project-management",
          name: "Program & project management",
          roles: [
            { id: "technical-program-manager", name: "Technical Program Manager", keywords: ["a", "b", "c", "d", "e", "f"], titles: ["tpm"], exclude_titles: [] },
            { id: "project-manager", name: "Project Manager", keywords: ["a", "b", "c", "d", "e", "f"], titles: [], exclude_titles: [] },
          ],
        },
      ],
    },
    isLoading: false,
  }),
}));

const tpm = { id: "tpm", name: "Technical Program Manager", field: "program-project-management", role: "technical-program-manager", keywords: [] };
const data = { id: "dpm", name: "Data Program Manager", field: "program-project-management", role: "technical-program-manager", keywords: [] };
const location = { location_home: "Denver, CO", location_preferred: [], remote_ok: null };
const proposal = { tracks: [tpm, data], location };

beforeEach(() => {
  save.mockReset().mockImplementation(async (source: { kind: string; track?: { id: string; name: string }; role?: { id: string; name: string } }) => {
    const t = source.kind === "proposed" ? source.track! : source.role!;
    return { id: t.id, name: t.name };
  });
  saver.ready = true;
  fire.mockClear();
  writeProposal("u1", proposal);
});
afterEach(() => {
  window.sessionStorage.clear();
  window.localStorage.clear();
});

describe("RoleStep", () => {
  it("suggests the top proposed track and one tap confirms it: one track saved, location merged, event fired", async () => {
    const onConfirmed = vi.fn();
    render(<RoleStep userId="u1" proposal={proposal} importError={null} onConfirmed={onConfirmed} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/looks like you're aiming for/i);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Technical Program Manager");
    await userEvent.setup({ delay: null }).click(screen.getByRole("button", { name: /yes, that's right/i }));
    await waitFor(() => expect(onConfirmed).toHaveBeenCalledWith({ id: "tpm", name: "Technical Program Manager" }));
    expect(save).toHaveBeenCalledTimes(1);
    expect(save).toHaveBeenCalledWith({ kind: "proposed", track: tpm }, location);
    expect(fire).toHaveBeenCalledWith("role_confirmed");
    expect(readConfirmedTrack("u1")).toBe("tpm");
    expect(readProposal("u1")).toBeNull(); // consumed
  });

  it("shows the shared coach copy", () => {
    render(<RoleStep userId="u1" proposal={proposal} importError={null} onConfirmed={vi.fn()} />);
    expect(screen.getByRole("heading", { level: 1, name: copy.roleQuestion("Technical Program Manager") })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: copy.ROLE_YES })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: copy.ROLE_OTHER })).toBeInTheDocument();
  });

  it("a double click on Yes saves once", async () => {
    let release: (v: unknown) => void = () => undefined;
    save.mockImplementationOnce(() => new Promise((resolve) => { release = () => resolve({ id: "tpm", name: "TPM" }); }));
    render(<RoleStep userId="u1" proposal={proposal} importError={null} onConfirmed={vi.fn()} />);
    const yes = screen.getByRole("button", { name: /yes, that's right/i });
    const user = userEvent.setup({ delay: null });
    await user.dblClick(yes);
    expect(save).toHaveBeenCalledTimes(1);
    release(null);
  });

  it("Something else shows the other proposed tracks and a typeahead over the taxonomy roles", async () => {
    const onConfirmed = vi.fn();
    render(<RoleStep userId="u1" proposal={proposal} importError={null} onConfirmed={onConfirmed} />);
    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByRole("button", { name: /something else/i }));
    expect(screen.getByRole("button", { name: "Data Program Manager" })).toBeInTheDocument();
    await user.type(screen.getByLabelText(/search roles/i), "tpm");
    const results = screen.getByRole("list", { name: /matching roles/i });
    await user.click(within(results).getByRole("button", { name: /Technical Program Manager/ }));
    await waitFor(() => expect(onConfirmed).toHaveBeenCalled());
    expect(save.mock.calls[0]![0]).toMatchObject({ kind: "taxonomy", role: { id: "technical-program-manager" } });
    expect(save.mock.calls[0]![1]).toEqual(location); // the location is about the person, not the role
  });

  it("with no proposal it asks what role and shows only the picker (the reload and the import-failed case)", () => {
    render(<RoleStep userId="u1" proposal={null} importError={null} onConfirmed={vi.fn()} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("What role are you aiming for?");
    expect(screen.getByLabelText(/search roles/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /yes, that's right/i })).toBeNull();
  });

  it("an import error is shown in plain words above the picker, with the paste option when offered", async () => {
    const onPaste = vi.fn();
    render(
      <RoleStep userId="u1" proposal={null} importError={{ message: "We couldn't read the roles in this resume", next: "role-picker" }} onConfirmed={vi.fn()} onPaste={onPaste} />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("We couldn't read the roles in this resume");
    await userEvent.setup({ delay: null }).click(screen.getByRole("button", { name: /paste a job/i }));
    expect(onPaste).toHaveBeenCalled();
  });

  it("will not save until answers and bases have loaded", () => {
    saver.ready = false;
    render(<RoleStep userId="u1" proposal={proposal} importError={null} onConfirmed={vi.fn()} />);
    expect(screen.getByRole("button", { name: /yes, that's right/i })).toBeDisabled();
  });

  it("a failed save is a plain sentence with a way forward, and Yes works again", async () => {
    save.mockRejectedValueOnce(new ApiError(500, { title: "x", status: 500 }, "x"));
    render(<RoleStep userId="u1" proposal={proposal} importError={null} onConfirmed={vi.fn()} />);
    await userEvent.setup({ delay: null }).click(screen.getByRole("button", { name: /yes, that's right/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong on our side");
    expect(screen.getByRole("button", { name: /yes, that's right/i })).not.toBeDisabled();
  });

  it("saves no blocks: neither the step nor the role helpers can reach the block endpoints", () => {
    const here = dirname(fileURLToPath(import.meta.url));
    const strip = (src: string) => src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^[ \t]*\/\/.*$/gm, "");
    for (const file of [join(here, "RoleStep.tsx"), join(here, "../../lib/coach/role.ts")]) {
      const code = strip(readFileSync(file, "utf8"));
      expect(code).not.toMatch(/usePutBlock|putBlock|profile\/blocks/);
    }
  });
});
