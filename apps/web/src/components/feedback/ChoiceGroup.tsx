import { useId } from "react";
import { cn } from "cn";

export type Choice<T extends string | number> = { value: T; label: string };

/**
 * Native radios inside <fieldset><legend>: Tab/arrow keys and screen readers work with no custom
 * key handling. Shared by the quick dialog and the survey so both behave the same by keyboard.
 */
export function ChoiceGroup<T extends string | number>({
  legend,
  options,
  value,
  onChange,
  optional,
  className,
}: {
  legend: string;
  options: ReadonlyArray<Choice<T>>;
  value: T | null | undefined;
  onChange: (value: T | null) => void;
  optional?: boolean;
  className?: string;
}) {
  const name = useId();
  return (
    <fieldset className={cn("min-w-0 space-y-1.5", className)}>
      <legend className="text-sm font-medium">
        {legend}
        {optional ? <span className="font-normal text-muted-foreground"> (optional)</span> : null}
      </legend>
      <div className="flex flex-wrap gap-2">
        {options.map((o) => (
          <label
            key={String(o.value)}
            className="flex min-h-9 cursor-pointer items-center gap-2 rounded-control border border-border px-3 text-sm has-checked:border-primary has-checked:bg-muted has-focus-visible:ring-3 has-focus-visible:ring-ring/50"
          >
            <input
              type="radio"
              name={name}
              className="accent-[var(--primary)]"
              checked={value === o.value}
              onChange={() => onChange(o.value)}
            />
            {o.label}
          </label>
        ))}
      </div>
      {optional && value != null ? (
        <button type="button" className="text-xs text-muted-foreground underline" onClick={() => onChange(null)}>
          Clear {legend.toLowerCase()}
        </button>
      ) : null}
    </fieldset>
  );
}
