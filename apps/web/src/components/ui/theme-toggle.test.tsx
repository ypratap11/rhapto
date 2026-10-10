import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { ThemeMenuItem, ThemeToggle, THEME_STORAGE_KEY } from "./theme-toggle";

afterEach(() => {
  document.documentElement.classList.remove("dark");
  localStorage.clear();
});

describe("ThemeToggle", () => {
  it("flips the dark class on <html> and remembers the choice", async () => {
    const user = userEvent.setup({ delay: null });
    render(<ThemeToggle />);
    const button = screen.getByRole("button", { name: /toggle theme/i });
    expect(button).toHaveAttribute("aria-pressed", "false");

    await user.click(button);
    expect(document.documentElement).toHaveClass("dark");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
    expect(button).toHaveAttribute("aria-pressed", "true");

    await user.click(button);
    expect(document.documentElement).not.toHaveClass("dark");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
  });
});

it("ThemeMenuItem shows the action in words and flips the theme", async () => {
  document.documentElement.classList.remove("dark");
  const user = userEvent.setup({ delay: null });
  render(<ThemeMenuItem className="x" />);
  const button = screen.getByRole("button", { name: "Dark mode" });
  await user.click(button);
  expect(document.documentElement.classList.contains("dark")).toBe(true);
  expect(screen.getByRole("button", { name: "Light mode" })).toBeInTheDocument();
});
