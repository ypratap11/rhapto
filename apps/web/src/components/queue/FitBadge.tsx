import { StatusBadge } from "@/components/ui/StatusBadge";
import { fitTone, formatFit } from "@/lib/fit";

export function FitBadge({ fit, trackName, minFit }: { fit: number | null; trackName: string | null; minFit: number | null }) {
  return (
    <StatusBadge tone={fitTone(fit, minFit)}>
      <span className="inline-flex items-center gap-1" title="Fit score 0–100 against your best track">
        {fit === null ? (
          "scoring…"
        ) : (
          <>
            <span className="font-mono">{formatFit(fit)}</span>
            {trackName ? <span>{trackName}</span> : null}
          </>
        )}
      </span>
    </StatusBadge>
  );
}
