import Link from "next/link";
import { cn } from "cn";

export type StatTone = "peach" | "mint" | "blue" | "amber";

// Every pair here is in lib/contrast/contrast.mjs (number, label and hint on each tinted tile, both themes).
const TONE: Record<StatTone, { box: string; number: string }> = {
  peach: { box: "bg-band-peach", number: "text-primary" },
  mint: { box: "bg-band-mint", number: "text-fit-high" },
  blue: { box: "bg-tone-blue-bg", number: "text-tone-blue" },
  amber: { box: "bg-fit-mid-bg", number: "text-fit-mid" },
};

type Common = {
  tone: StatTone;
  value: number | string;
  label: string;
  hint?: string;
  /** Extra classes for the hint line, e.g. `max-sm:hidden` to drop it on phones. */
  hintClassName?: string;
  /** Zero or unknown: the number goes quiet. */
  muted?: boolean;
  className?: string;
};

/**
 * A coloured count tile: big serif number, label, one-line hint. A link when given `href`, otherwise a
 * button. A button with `pressed` set is a toggle (aria-pressed) and shows a darker outline while on.
 * At least 44px tall, visible focus ring, lifts on hover only when motion is allowed.
 */
export function StatTile(props: Common & ({ href: string; onClick?: never; pressed?: never } | { href?: undefined; onClick: () => void; pressed?: boolean })) {
  const { tone, value, label, hint, hintClassName, muted, className } = props;
  const t = TONE[tone];
  const classes = cn(
    "flex min-h-11 flex-col gap-0.5 rounded-2xl border border-transparent px-[18px] py-4 text-left text-foreground no-underline outline-none",
    "transition-[transform,box-shadow,border-color] focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 motion-safe:hover:-translate-y-0.5 motion-safe:hover:shadow-card",
    t.box,
    props.href === undefined && props.pressed ? "border-foreground shadow-card" : null,
    className,
  );
  const body = (
    <>
      <span className={cn("font-serif text-[34px] leading-none font-semibold tabular-nums", muted ? "text-muted-foreground" : t.number)}>{value}</span>
      <span className="font-medium">{label}</span>
      {hint ? <span className={cn("text-[0.8rem] text-muted-foreground", hintClassName)}>{hint}</span> : null}
    </>
  );
  if (props.href !== undefined) {
    return (
      <Link href={props.href} className={classes}>
        {body}
      </Link>
    );
  }
  return (
    <button type="button" onClick={props.onClick} aria-pressed={props.pressed} className={classes}>
      {body}
    </button>
  );
}
