import Link from "next/link";
import type { CoachError } from "@/lib/coach/errors";

export type TranscriptItem = { label: string; value: string };

/** One coach screen: the steps already taken (short, above), the current question, and the way out.
 * Every screen carries "Skip to the full app" (spec 2). */
export function CoachFrame({
  title,
  hint,
  transcript = [],
  children,
}: {
  title: string;
  hint?: string;
  transcript?: TranscriptItem[];
  children: React.ReactNode;
}) {
  return (
    <div className="mx-auto max-w-2xl space-y-5">
      {transcript.length > 0 ? (
        <ol aria-label="So far" className="space-y-1 text-sm text-muted-foreground">
          {transcript.map((item) => (
            <li key={item.label}>
              {item.label}: <span className="text-foreground">{item.value}</span>
            </li>
          ))}
        </ol>
      ) : null}
      <section className="space-y-4 rounded-card border border-border bg-surface p-6 shadow-card">
        <h1 className="font-heading text-2xl font-medium">{title}</h1>
        {hint ? <p className="text-sm text-muted-foreground">{hint}</p> : null}
        {children}
      </section>
      <p className="text-sm">
        <Link href="/dashboard" className="text-muted-foreground underline underline-offset-4 hover:text-foreground">
          Skip to the full app
        </Link>
      </p>
    </div>
  );
}

/** A plain-words error with its one way forward. Renders nothing for null. */
export function CoachErrorNote({ error }: { error: CoachError | null }) {
  if (!error) return null;
  const external = error.link?.href.startsWith("http");
  return (
    <div role="alert" className="rounded-control border-l-4 border-destructive bg-surface-muted p-3 text-sm">
      <p>{error.message}</p>
      {error.link ? (
        <p className="mt-1">
          <a
            href={error.link.href}
            target={external ? "_blank" : undefined}
            rel={external ? "noreferrer" : undefined}
            className="text-primary underline underline-offset-4"
          >
            {error.link.label}
          </a>
        </p>
      ) : null}
    </div>
  );
}
