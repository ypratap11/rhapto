import type { LucideIcon } from "lucide-react";
import { cn } from "cn";

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon: LucideIcon;
  title: string;
  description?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      data-slot="empty-state"
      className={cn("flex flex-col items-center justify-center gap-3 px-6 py-12 text-center", className)}
    >
      <span
        data-slot="empty-state-icon"
        aria-hidden="true"
        className="flex size-16 items-center justify-center rounded-full bg-glow-mid dark:bg-surface-muted"
      >
        <Icon className="size-8 text-muted-foreground" strokeWidth={1.5} />
      </span>
      <p className="font-heading text-base font-semibold tracking-tight text-foreground">{title}</p>
      {description ? <p className="max-w-sm text-sm text-muted-foreground">{description}</p> : null}
      {action ? <div className="pt-1">{action}</div> : null}
    </div>
  );
}
