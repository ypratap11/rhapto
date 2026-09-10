"use client";

import { Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError } from "@/lib/api/client";
import { useAnswers, usePutAnswers } from "@/lib/api/queries";

type Row = { key: string; value: string };

export function AnswersTab() {
  const answers = useAnswers();
  if (answers.isLoading) return <Skeleton className="h-40 w-full" />;
  if (answers.error) return <ApiErrorBanner error={answers.error} />;
  // Key by the fetched data's identity so the editable copy is (re)initialized only when the
  // server data actually changes (e.g. after a save), not on every render — avoids syncing
  // props into state via an effect.
  return <AnswersBody key={JSON.stringify(answers.data ?? {})} initial={answers.data ?? {}} />;
}

function AnswersBody({ initial }: { initial: Record<string, string> }) {
  const put = usePutAnswers();
  const [rows, setRows] = useState<Row[]>(() => Object.entries(initial).map(([key, value]) => ({ key, value })));

  function setRow(index: number, patch: Partial<Row>) {
    setRows((r) => r.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  function removeRow(index: number) {
    setRows((r) => r.filter((_, i) => i !== index));
  }

  async function save() {
    const map: Record<string, string> = {};
    for (const row of rows) {
      const key = row.key.trim();
      if (key) map[key] = row.value;
    }
    try {
      await put.mutateAsync(map);
      toast.success("Saved answers");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not save answers");
    }
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        <code className="font-mono text-xs">name</code>, <code className="font-mono text-xs">email</code>, <code className="font-mono text-xs">phone</code>, <code className="font-mono text-xs">location</code>, and{" "}
        <code className="font-mono text-xs">links</code> feed the resume header. Other keys answer application-form questions verbatim.
      </p>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Key</TableHead>
            <TableHead>Value</TableHead>
            <TableHead className="w-10" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row, i) => (
            <TableRow key={i}>
              <TableCell>
                <Label htmlFor={`answer-key-${i}`} className="sr-only">
                  Key {i + 1}
                </Label>
                <Input id={`answer-key-${i}`} value={row.key} onChange={(e) => setRow(i, { key: e.target.value })} placeholder="key" />
              </TableCell>
              <TableCell>
                <Label htmlFor={`answer-value-${i}`} className="sr-only">
                  Value {i + 1}
                </Label>
                <Input id={`answer-value-${i}`} value={row.value} onChange={(e) => setRow(i, { value: e.target.value })} placeholder="value" />
              </TableCell>
              <TableCell>
                <Button variant="ghost" size="icon" aria-label={`Remove row ${i + 1}`} onClick={() => removeRow(i)}>
                  <Trash2 className="size-4" aria-hidden />
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <div className="flex justify-between">
        <Button variant="outline" onClick={() => setRows((r) => [...r, { key: "", value: "" }])}>
          Add row
        </Button>
        <Button onClick={save} disabled={put.isPending}>
          Save
        </Button>
      </div>
    </div>
  );
}
