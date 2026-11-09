import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { COMMERCIAL_DESCRIPTION, COMMERCIAL_POSTER, COMMERCIAL_SRC, CommercialVideo } from "./CommercialVideo";

type Cb = (entries: { isIntersecting: boolean }[]) => void;

describe("CommercialVideo", () => {
  let io: { cb: Cb } | null;
  let play: ReturnType<typeof vi.fn>;

  /** wide: the min-width query matches; reduce: prefers-reduced-motion matches. */
  const setMedia = (wide: boolean, reduce: boolean) =>
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      writable: true,
      value: (q: string) => ({
        matches: q.includes("reduced-motion") ? reduce : q.includes("min-width") ? wide : false,
        media: q,
        addEventListener() {},
        removeEventListener() {},
      }),
    });
  const intersect = (isIntersecting: boolean) => act(() => io?.cb([{ isIntersecting }]));
  const video = () => document.querySelector("video") as HTMLVideoElement;

  beforeEach(() => {
    io = null;
    play = vi.fn(() => Promise.resolve());
    HTMLMediaElement.prototype.play = play as unknown as () => Promise<void>;
    Object.defineProperty(window, "IntersectionObserver", {
      configurable: true,
      writable: true,
      value: class {
        constructor(cb: Cb) {
          io = { cb };
        }
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    });
    setMedia(true, false);
  });
  afterEach(() => {
    Reflect.deleteProperty(window, "matchMedia");
    Reflect.deleteProperty(window, "IntersectionObserver");
  });

  it("renders a labelled video with poster, controls and no download until played", () => {
    render(<CommercialVideo />);
    const v = video();
    expect(v.getAttribute("src")).toBe(COMMERCIAL_SRC);
    expect(v.getAttribute("poster")).toBe(COMMERCIAL_POSTER);
    expect(v.controls).toBe(true);
    expect(v.getAttribute("preload")).toBe("none");
    expect(v.hasAttribute("playsinline")).toBe(true);
    expect(v.getAttribute("aria-label")).toMatch(/\S/);
    expect(v.loop).toBe(false);
    expect(v.muted).toBe(false); // a tap plays with sound
  });

  it("has a heading and a one-sentence plain description tied to the video", () => {
    render(<CommercialVideo />);
    expect(screen.getByRole("heading", { level: 2 })).toBeInTheDocument();
    const desc = screen.getByText(COMMERCIAL_DESCRIPTION);
    expect(video().getAttribute("aria-describedby")).toBe(desc.id);
    expect(COMMERCIAL_DESCRIPTION.match(/[.!?]/g)).toHaveLength(1);
  });

  it("keeps the copy free of only/first claims and of any promise to submit", () => {
    const { container } = render(<CommercialVideo />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/\b(only|first)\b/i);
    expect(text).not.toMatch(/\bsubmits?\b|\bapplies for you\b|auto-?apply/i);
  });

  it("autoplays muted, once, when visible on a wide screen", () => {
    render(<CommercialVideo />);
    expect(play).not.toHaveBeenCalled();
    intersect(true);
    expect(play).toHaveBeenCalledTimes(1);
    expect(video().muted).toBe(true);
    intersect(false);
    intersect(true);
    expect(play).toHaveBeenCalledTimes(1);
  });

  it("does not autoplay before it is visible", () => {
    render(<CommercialVideo />);
    intersect(false);
    expect(play).not.toHaveBeenCalled();
  });

  it("never autoplays on a phone", () => {
    setMedia(false, false);
    render(<CommercialVideo />);
    intersect(true);
    expect(play).not.toHaveBeenCalled();
    expect(video().muted).toBe(false);
  });

  it("never autoplays under reduced motion, even on a wide screen", () => {
    setMedia(true, true);
    render(<CommercialVideo />);
    intersect(true);
    expect(play).not.toHaveBeenCalled();
  });

  it("does not autoplay when IntersectionObserver is missing", () => {
    Reflect.deleteProperty(window, "IntersectionObserver");
    render(<CommercialVideo />);
    expect(play).not.toHaveBeenCalled();
  });

  it("survives a blocked autoplay promise", async () => {
    play.mockImplementation(() => Promise.reject(new Error("NotAllowedError")));
    render(<CommercialVideo />);
    intersect(true);
    await Promise.resolve();
    expect(video()).toBeInTheDocument();
  });
});
