"use client";

import { useId, useRef, useState } from "react";
import { toast } from "sonner";
import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ApiError } from "@/lib/api/client";
import { useDeleteResumeDocument, useResumeDocument, useUploadResumeDocument, type DocParagraph } from "@/lib/api/queries";
import { formatRelative } from "@/lib/format";

// Roles the tune-mode rewrite is allowed to touch (apps/api's EDITABLE_ROLES); everything
// else (name, contact, headings, org/title lines, credentials) is structural and protected.
const EDITABLE_ROLES = new Set(["summary", "competency", "skill", "bullet"]);

export function ResumeDocumentTab() {
  const resumeDocument = useResumeDocument();
  const upload = useUploadResumeDocument();
  const remove = useDeleteResumeDocument();
  const inputRef = useRef<HTMLInputElement>(null);
  const inputId = useId();
  const [confirmDelete, setConfirmDelete] = useState(false);

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      await upload.mutateAsync(file);
      toast.success(`Uploaded ${file.name}`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not upload the resume document");
    } finally {
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  async function handleDelete() {
    try {
      await remove.mutateAsync();
      toast.success("Deleted the resume document");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not delete the resume document");
    } finally {
      setConfirmDelete(false);
    }
  }

  if (resumeDocument.isLoading) return <Skeleton className="h-40 w-full" />;
  if (resumeDocument.error) return <ApiErrorBanner error={resumeDocument.error} />;

  const doc = resumeDocument.data;
  const fileInput = (
    <input
      ref={inputRef}
      id={inputId}
      type="file"
      accept=".docx"
      aria-label="Resume document"
      className={doc ? "sr-only" : "block text-sm"}
      onChange={handleFile}
    />
  );

  if (!doc) {
    return (
      <Card className="space-y-3 p-4">
        <div>
          <h2 className="font-heading text-base font-medium">Resume document</h2>
          <p className="text-sm text-muted-foreground">Upload your resume (.docx) to tailor it directly. Tune mode switches on automatically.</p>
        </div>
        <div className="space-y-1">
          <Label htmlFor={inputId}>Resume file</Label>
          {fileInput}
        </div>
      </Card>
    );
  }

  const paragraphById = new Map<string, DocParagraph>(doc.document.paragraphs.map((p) => [p.id, p]));

  return (
    <Card className="space-y-4 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-heading text-base font-medium">{doc.filename}</h2>
          <p className="text-sm text-muted-foreground">Uploaded {formatRelative(doc.uploaded_at)}</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => inputRef.current?.click()} disabled={upload.isPending}>
            Replace
          </Button>
          <Button variant="destructive" aria-label={`Delete ${doc.filename}`} onClick={() => setConfirmDelete(true)} disabled={remove.isPending}>
            Delete
          </Button>
        </div>
      </div>
      {fileInput}
      <div className="space-y-3">
        <h3 className="text-sm font-medium">Parsed as</h3>
        {doc.document.sections.map((section) => (
          <div key={section.heading} className="space-y-1.5">
            <p className="text-sm font-medium">{section.heading}</p>
            <ul className="space-y-1.5">
              {section.paragraph_ids.map((id) => {
                const paragraph = paragraphById.get(id);
                if (!paragraph) return null;
                return (
                  <li key={id} className="flex items-start gap-2 text-sm">
                    <StatusBadge tone={EDITABLE_ROLES.has(paragraph.role) ? "green" : "zinc"}>{paragraph.role}</StatusBadge>
                    <span className="text-muted-foreground">{paragraph.text}</span>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>
      <AlertDialog open={confirmDelete} onOpenChange={(o) => !o && setConfirmDelete(false)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {doc.filename}?</AlertDialogTitle>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
