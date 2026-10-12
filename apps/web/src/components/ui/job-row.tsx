import { FitRing } from "@/components/ui/fit-ring";
import { cn } from "cn";

/**
 * The shell of one job in a list: fit ring, one-line title (wraps on phones), a meta line, and actions on
 * the right (below on phones). Hovering turns the border to the primary colour. Callers fill `meta` with
 * company, location and pills, and `actions` with whatever belongs there (buttons on the Dashboard, a button-looking
 * span on My resumes, where the whole row is one link). The Dashboard and My resumes share it; Jobs uses `JobCard`.
 * Renders an `li` by default, for use inside a `ul`.
 */
export function JobRow({
  fit,
  title,
  meta,
  actions,
  as: Tag = "li",
  className,
}: {
  fit: number | null;
  title: React.ReactNode;
  meta?: React.ReactNode;
  actions?: React.ReactNode;
  as?: "li" | "div";
  className?: string;
}) {
  return (
    <Tag
      data-slot="job-row"
      className={cn(
        "grid grid-cols-[auto_minmax(0,1fr)] items-center gap-x-3.5 gap-y-2 rounded-2xl border border-border bg-surface px-4 py-3.5 transition-[border-color,box-shadow] hover:border-primary hover:shadow-card sm:grid-cols-[auto_minmax(0,1fr)_auto]",
        className,
      )}
    >
      <FitRing fit={fit} size={52} />
      <div className="min-w-0">
        <p className="leading-snug font-semibold sm:truncate">{title}</p>
        {meta ? <div className="mt-0.5 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-sm text-muted-foreground">{meta}</div> : null}
      </div>
      {actions ? <div className="col-span-2 flex items-center justify-end gap-1.5 sm:col-span-1">{actions}</div> : null}
    </Tag>
  );
}
