import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { AlertOut } from "@/lib/admin/types";
import { cn } from "cn";

const DOT = { warn: "bg-fit-mid", info: "bg-fit-high" } as const;

export function AttentionList({ alerts }: { alerts: AlertOut[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="font-heading text-lg">Needs your attention</CardTitle>
      </CardHeader>
      <CardContent>
        {alerts.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nothing needs your attention</p>
        ) : (
          <ul className="flex flex-col divide-y divide-border">
            {alerts.map((a) => (
              <li key={a.id} className="flex items-start gap-3 py-3 first:pt-0 last:pb-0">
                <span data-testid={`dot-${a.id}`} aria-hidden="true" className={cn("mt-1.5 size-2.5 shrink-0 rounded-full", DOT[a.tone])} />
                <div className="min-w-0">
                  <p className="font-medium text-foreground">{a.title}</p>
                  <p className="text-sm text-muted-foreground">{a.detail}</p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
