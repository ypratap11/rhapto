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

/** Plain names for the line kinds Rhapto finds in an uploaded resume; anything unlisted shows as-is. */
const ROLE_LABELS: Record<string, string> = { org: "employer", title: "job title", competency: "strength" };

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
      toast.error(err instanceof ApiError ? err.message : "Could not upload your resume file");
    } finally {
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  async function handleDelete() {
    try {
      await remove.mutateAsync();
      toast.success("Deleted your resume file");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not delete your resume file");
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
      aria-label="Resume file"
      className={doc ? "sr-only" : "block text-sm"}
      onChange={handleFile}
    />
  );

  if (!doc) {
    return (
      <Card className="space-y-3 p-4">
        <div>
          <h2 className="font-heading text-base font-medium">Your resume file</h2>
          <p className="text-sm text-muted-foreground">Upload your resume (.docx). Light touch rewords a few lines of this file for each job and leaves the rest as it is.</p>
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
        <h3 className="text-sm font-medium">How Rhapto reads it</h3>
        <p className="text-xs text-muted-foreground">Lines with a green label can be reworded. Everything else stays exactly as written.</p>
        {doc.document.sections.map((section) => (
          <div key={section.heading} className="space-y-1.5">
            <p className="text-sm font-medium">{section.heading}</p>
            <ul className="space-y-1.5">
              {section.paragraph_ids.map((id) => {
                const paragraph = paragraphById.get(id);
                if (!paragraph) return null;
                return (
                  <li key={id} className="flex items-start gap-2 text-sm">
                    <StatusBadge tone={EDITABLE_ROLES.has(paragraph.role) ? "high" : "muted"}>{ROLE_LABELS[paragraph.role] ?? paragraph.role}</StatusBadge>
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
