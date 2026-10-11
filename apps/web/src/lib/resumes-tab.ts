export type ResumesTab = "review" | "ready" | "blocked";

function isResumesTab(value: string | null): value is ResumesTab {
  return value === "review" || value === "ready" || value === "blocked";
}

// The old /packages route 307-redirected to /resumes with its ?filter= intact, including the retired
// "all" value. That value, the retired "applied" tab, and any other unrecognized one fall back to
// "review". Lives here, not in page.tsx: a Next page file may export only its default component.
export function resolveTab(params: URLSearchParams): ResumesTab {
  const raw = params.get("tab") ?? params.get("filter");
  return isResumesTab(raw) ? raw : "review";
}
