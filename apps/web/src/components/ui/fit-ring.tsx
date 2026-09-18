import { cn } from "cn";

export type FitBand = "high" | "mid" | "low" | "none";

/** Same thresholds the queue has always used: 75 and above is a strong fit, 60 and above is worth a look. */
export function fitBand(fit: number | null | undefined): FitBand {
  if (fit === null || fit === undefined) return "none";
  if (fit >= 75) return "high";
  if (fit >= 60) return "mid";
  return "low";
}

const BAND_TEXT: Record<FitBand, string> = {
  high: "text-fit-high",
  mid: "text-fit-mid",
  low: "text-fit-low",
  none: "text-muted-foreground",
};

const STROKE = 3;

export function FitRing({
  fit,
  size = 36,
  className,
}: {
  fit: number | null;
  size?: number;
  className?: string;
}) {
  const band = fitBand(fit);
  const radius = (size - STROKE) / 2;
  const circumference = 2 * Math.PI * radius;
  const fraction = fit === null ? 0 : Math.min(100, Math.max(0, fit)) / 100;
  const center = size / 2;

  return (
    <div
      data-slot="fit-ring"
      data-band={band}
      role="img"
      aria-label={fit === null ? "Fit not scored yet" : `Fit ${fit}`}
      title={fit === null ? "Not scored yet" : "Fit score 0–100 against your best track"}
      className={cn("relative inline-flex shrink-0 items-center justify-center", BAND_TEXT[band], className)}
      style={{ width: size, height: size }}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true" className="-rotate-90">
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          strokeWidth={STROKE}
          stroke={fit === null ? "currentColor" : "var(--border)"}
          strokeDasharray={fit === null ? "3 4" : undefined}
          opacity={fit === null ? 0.5 : 1}
        />
        {fit !== null ? (
          <circle
            cx={center}
            cy={center}
            r={radius}
            fill="none"
            strokeWidth={STROKE}
            stroke="currentColor"
            strokeLinecap="round"
            strokeDasharray={`${circumference * fraction} ${circumference}`}
          />
        ) : null}
      </svg>
      <span className="absolute font-mono text-[12px] leading-none font-medium tabular-nums">
        {fit === null ? "—" : fit}
      </span>
    </div>
  );
}
