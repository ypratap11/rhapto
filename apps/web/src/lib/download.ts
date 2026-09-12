import { ApiError, apiUrl, authHeaders, type Problem } from "./api/client";

export async function downloadAuthenticated(path: string, filename: string): Promise<void> {
  const response = await fetch(apiUrl(path), { headers: authHeaders() });
  if (!response.ok) {
    let problem: Problem | null = null;
    try {
      problem = (await response.json()) as Problem;
    } catch {
      problem = null;
    }
    throw new ApiError(response.status, problem, `HTTP ${response.status}`);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Revoking synchronously can invalidate the URL before the browser's download
  // handler has consumed it in some browsers; defer to the next tick instead.
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function resumeFilename(name: string | null | undefined, kind: "pdf" | "docx" | "zip"): string {
  const stem = (name ?? "").replace(/[^A-Za-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || "Resume";
  return kind === "zip" ? `${stem}_Package.zip` : `${stem}_Resume.${kind}`;
}
