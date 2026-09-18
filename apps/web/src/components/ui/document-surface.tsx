import { cn } from "cn";

/** The "paper" panel the review page's resume and changes panes sit on. */
export function DocumentSurface({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      data-slot="document-surface"
      className={cn("rounded-card border border-border bg-surface p-8 shadow-card", className)}
    >
      {children}
    </div>
  );
}
