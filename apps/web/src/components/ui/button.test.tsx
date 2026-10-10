import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Badge } from "./badge";
import { Button } from "./button";

const VARIANTS = ["default", "outline", "secondary", "ghost", "destructive"] as const;
const SIZES = ["default", "xs", "sm", "lg", "icon", "icon-xs", "icon-sm", "icon-lg"] as const;

describe("Button shape", () => {
  it("is a pill or circle for every variant except link, at every size", () => {
    for (const variant of VARIANTS) {
      for (const size of SIZES) {
        const { unmount } = render(<Button variant={variant} size={size}>x</Button>);
        const cls = screen.getByRole("button").className;
        expect(cls, `${variant}/${size}`).toContain("rounded-full");
        expect(cls, `${variant}/${size}`).not.toContain("rounded-[min");
        expect(cls, `${variant}/${size}`).not.toMatch(/rounded-lg/);
        unmount();
      }
    }
  });

  it("keeps the link variant a plain text link shape", () => {
    render(<Button variant="link">x</Button>);
    expect(screen.getByRole("button").className).not.toContain("rounded-full");
  });

  it("hovers the default variant to --primary-hover, never a translucent primary", () => {
    render(<Button>x</Button>);
    const cls = screen.getByRole("button").className;
    expect(cls).toContain("hover:bg-primary-hover");
    expect(cls).not.toContain("bg-primary/80");
  });

  it("lg has px-4", () => {
    render(<Button size="lg">x</Button>);
    expect(screen.getByRole("button").className).toContain("px-4");
  });
});

describe("Badge hover", () => {
  it("uses --primary-hover on links", () => {
    render(<Badge render={<a href="/x" />}>x</Badge>);
    const cls = screen.getByRole("link").className;
    expect(cls).toContain("[a]:hover:bg-primary-hover");
    expect(cls).not.toContain("bg-primary/80");
  });
});
