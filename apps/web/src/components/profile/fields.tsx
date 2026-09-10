"use client";

import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";

/**
 * A checkbox with a click-to-toggle text label.
 *
 * The shadcn/base-ui Checkbox renders both an ARIA `role="checkbox"` node and a hidden native
 * `<input>` for form semantics. Pairing it with a plain `<Label htmlFor>` associates *both* nodes
 * with the same label text, which breaks `getByLabelText` (it finds two matches) and is
 * ambiguous for assistive tech. Labelling the visible checkbox directly via `aria-labelledby`
 * (pointed at a plain `<label>` with its own `id`, not linked through `htmlFor`) keeps the
 * association to a single element while a manual `onClick` preserves click-to-toggle.
 */
export function CheckboxField({ id, label, checked, onCheckedChange, disabled }: { id: string; label: string; checked: boolean; onCheckedChange: (checked: boolean) => void; disabled?: boolean }) {
  const labelId = `${id}-label`;
  return (
    <div className="flex items-center gap-2">
      <Checkbox aria-labelledby={labelId} checked={checked} onCheckedChange={(v) => onCheckedChange(v === true)} disabled={disabled} />
      <label id={labelId} className="cursor-pointer text-sm leading-none font-medium select-none" onClick={() => !disabled && onCheckedChange(!checked)}>
        {label}
      </label>
    </div>
  );
}

/** Same rationale as {@link CheckboxField}, for the Switch primitive. */
export function SwitchField({ id, label, checked, onCheckedChange, disabled }: { id: string; label: string; checked: boolean; onCheckedChange: (checked: boolean) => void; disabled?: boolean }) {
  const labelId = `${id}-label`;
  return (
    <div className="flex items-center gap-2">
      <Switch aria-labelledby={labelId} checked={checked} onCheckedChange={(v) => onCheckedChange(v === true)} disabled={disabled} />
      <label id={labelId} className="cursor-pointer text-sm leading-none font-medium select-none" onClick={() => !disabled && onCheckedChange(!checked)}>
        {label}
      </label>
    </div>
  );
}
