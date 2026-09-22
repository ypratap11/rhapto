"use client";

import { useId, useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api/client";
import { useImportProfile, useImportResume, type ResumeImportOut } from "@/lib/api/queries";
import { downloadAuthenticated } from "@/lib/download";
import { ImportResume } from "./ImportResume";

export function ImportExport() {
  const importProfile = useImportProfile();
  const importResume = useImportResume();
  const fileInputId = useId();
  const resumeInputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const resumeInputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [exporting, setExporting] = useState(false);
  const [proposal, setProposal] = useState<ResumeImportOut | null>(null);

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

  async function runResumeImport(file: File) {
    try {
      setProposal(await importResume.mutateAsync(file));
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not read that resume");
    } finally {
      if (resumeInputRef.current) resumeInputRef.current.value = "";
    }
  }

  // No self-wrapping Card or title here: the caller (Settings) supplies both, so this renders just
  // the description and controls as content for whatever Card it's placed inside.
  return (
    <div className="space-y-4">
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
      <div className="space-y-1 border-t border-border pt-3">
        <Label htmlFor={resumeInputId}>Import from a resume (.docx)</Label>
        <p className="text-xs text-muted-foreground">
          Rhapto proposes blocks, tracks and location from your resume. Nothing is saved until you review and accept it.
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <input
            ref={resumeInputRef}
            id={resumeInputId}
            type="file"
            accept=".docx"
            className="block text-sm"
            disabled={importResume.isPending}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void runResumeImport(file);
            }}
          />
          {importResume.isPending ? <p className="text-sm text-muted-foreground">Reading your resume…</p> : null}
        </div>
      </div>
      <Dialog open={proposal !== null} onOpenChange={(o) => !o && setProposal(null)}>
        <DialogContent className="flex max-h-[85vh] flex-col overflow-hidden sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Review your imported resume</DialogTitle>
          </DialogHeader>
          {proposal ? (
            <div className="min-h-0 flex-1 overflow-y-auto pr-1">
              <ImportResume proposal={proposal} onConfirm={() => undefined} onCancel={() => setProposal(null)} onDone={() => setProposal(null)} />
            </div>
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}
