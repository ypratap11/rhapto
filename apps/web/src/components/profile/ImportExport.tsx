"use client";

import { useId, useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api/client";
import { useImportProfile } from "@/lib/api/queries";
import { downloadAuthenticated } from "@/lib/download";

export function ImportExport() {
  const importProfile = useImportProfile();
  const fileInputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [exporting, setExporting] = useState(false);

  async function runImport() {
    if (files.length === 0) return;
    try {
      const result = await importProfile.mutateAsync(files);
      toast.success(`Imported ${result.blocks} blocks, ${result.bases} bases, ${result.tracks} tracks, ${result.guardrails} guardrails`);
      setFiles([]);
      if (inputRef.current) inputRef.current.value = "";
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not import the profile YAML");
    }
  }

  async function runExport() {
    setExporting(true);
    try {
      await downloadAuthenticated("/api/v1/profile/export", "profile.zip");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not export the profile");
    } finally {
      setExporting(false);
    }
  }

  // No self-wrapping Card or title here: the caller (Settings) supplies both, so this renders just
  // the description and controls as content for whatever Card it's placed inside.
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Your profile lives in the database now. Import YAML files to replace it, or export it back to YAML — <code className="font-mono text-xs">rhapto profile export</code> writes the same files locally.
      </p>
      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1">
          <Label htmlFor={fileInputId}>Profile YAML files</Label>
          <input
            ref={inputRef}
            id={fileInputId}
            type="file"
            multiple
            accept=".yaml,.yml"
            className="block text-sm"
            onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
          />
        </div>
        <Button onClick={runImport} disabled={files.length === 0 || importProfile.isPending}>
          Import
        </Button>
        <Button variant="outline" onClick={runExport} disabled={exporting}>
          Export YAML
        </Button>
      </div>
    </div>
  );
}
