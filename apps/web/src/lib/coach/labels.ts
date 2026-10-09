export function matchLabel(fit: number | null | undefined, minFit: number): "Strong match" | "Good match" {
  return fit !== null && fit !== undefined && fit >= minFit ? "Strong match" : "Good match";
}

export function runsLeftLine(left: number | null | undefined): string | null {
  if (left === null || left === undefined) return null;
  if (left <= 0) return "No free runs left. Add your own AI key in Settings to keep going.";
  return `${left} free ${left === 1 ? "run" : "runs"} left`;
}
