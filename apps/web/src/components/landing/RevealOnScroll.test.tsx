import { render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RevealOnScroll } from "./RevealOnScroll";

type Cb = (entries: { isIntersecting: boolean; target: Element }[]) => void;
let cb: Cb;
const unobserve = vi.fn();
const setMedia = (reduce: boolean) =>
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: (q: string) => ({ matches: reduce, media: q, addEventListener() {}, removeEventListener() {} }),
  });
function page() {
  document.body.innerHTML = '<section class="reveal" id="a"></section><section class="reveal" id="b"></section>';
  const [a, b] = [document.getElementById("a")!, document.getElementById("b")!];
  a.getBoundingClientRect = () => ({ top: 10 }) as DOMRect; // on screen at load
  b.getBoundingClientRect = () => ({ top: 5000 }) as DOMRect; // below the fold
  return { a, b };
}

beforeEach(() => {
  setMedia(false);
  unobserve.mockClear();
  Object.defineProperty(window, "IntersectionObserver", {
    configurable: true,
    writable: true,
    value: class {
      constructor(c: Cb) {
        cb = c;
      }
      observe() {}
      unobserve = unobserve;
      disconnect() {}
    },
  });
});
afterEach(() => {
  Reflect.deleteProperty(window, "matchMedia");
  Reflect.deleteProperty(window, "IntersectionObserver");
  document.body.innerHTML = "";
});

describe("RevealOnScroll", () => {
  it("arms only the sections below the fold; the one on screen stays visible", () => {
    const { a, b } = page();
    render(<RevealOnScroll />);
    expect(a.dataset.reveal).toBeUndefined();
    expect(b.dataset.reveal).toBe("armed");
  });

  it("reveals once on first intersection and never re-hides on scroll-up", () => {
    const { b } = page();
    render(<RevealOnScroll />);
    cb([{ isIntersecting: true, target: b }]);
    expect(b.dataset.reveal).toBe("in");
    expect(unobserve).toHaveBeenCalledWith(b);
    cb([{ isIntersecting: false, target: b }]); // scrolled back up
    expect(b.dataset.reveal).toBe("in");
  });

  it("arms nothing under prefers-reduced-motion", () => {
    setMedia(true);
    const { b } = page();
    render(<RevealOnScroll />);
    expect(b.dataset.reveal).toBeUndefined();
  });

  it("arms nothing where IntersectionObserver is missing (content stays visible)", () => {
    Reflect.deleteProperty(window, "IntersectionObserver");
    const { b } = page();
    render(<RevealOnScroll />);
    expect(b.dataset.reveal).toBeUndefined();
  });

  it("unmount un-hides anything still armed", () => {
    const { b } = page();
    const { unmount } = render(<RevealOnScroll />);
    unmount();
    expect(b.dataset.reveal).toBeUndefined();
  });
});
