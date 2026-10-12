import { cn } from "cn";

/**
 * The signed-in pages' hero band: a warm wash behind the page title, summary and (optionally) one card on
 * the right, with room below for tiles or filters. Dashboard, Jobs, My resumes and Profile all use it.
 *
 * Like HeroBand's glow tone, the content stays in main's own column (so it lines up with the header logo
 * and the sections below) and only the wash breaks out, as a viewport-wide ::before centred on that column.
 * `-mt-8` cancels main's top padding so the wash starts right under the header. Layout is algebraic, not
 * something jsdom can render: confirm it with a screenshot.
 *
 * `title` is the page's one h1. `aside` sits to the right from md and goes full width below on phones.
 */
export function PageHero({
  title,
  subtitle,
  aside,
  children,
  className,
}: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  aside?: React.ReactNode;
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      data-testid="page-hero"
      className={cn(
        "relative isolate -mt-8 mb-8 pt-10 before:pointer-events-none before:absolute before:inset-y-0 before:left-1/2 before:-z-10 before:w-screen before:-translate-x-1/2 before:bg-page-hero",
        className,
      )}
    >
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
        <div className="min-w-0">
          <h1 className="font-serif text-[clamp(1.75rem,4vw,2.5rem)] leading-[1.15] font-semibold text-balance">{title}</h1>
          {subtitle ? <div className="mt-1.5 text-muted-foreground">{subtitle}</div> : null}
        </div>
        {aside ? <div className="w-full md:w-auto md:max-w-lg">{aside}</div> : null}
      </div>
      {children ? <div className="mt-7">{children}</div> : null}
    </section>
  );
}
