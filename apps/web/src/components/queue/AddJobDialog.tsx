"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api/client";
import { useCreateJob } from "@/lib/api/queries";

export function AddJobDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const router = useRouter();
  const create = useCreateJob();
  const [mode, setMode] = useState<"paste" | "url">("paste");
  const [text, setText] = useState("");
  const [url, setUrl] = useState("");
  const [company, setCompany] = useState("");
  const [title, setTitle] = useState("");
  const [location, setLocation] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [existing, setExisting] = useState<string | null>(null);

  async function submit() {
    setError(null);
    setExisting(null);
    if (mode === "paste" && text.trim().length < 50) return setError("Paste at least 50 characters of the job description.");
    if (mode === "url" && !/^https?:\/\//i.test(url.trim())) return setError("Enter an http(s) URL.");
    try {
      const job = await create.mutateAsync({
        jd_text: mode === "paste" ? text : null,
        url: mode === "url" ? url.trim() : null,
        company: company.trim() || null,
        title: title.trim() || null,
        location: location.trim() || null,
      });
      toast.success("Job added");
      onOpenChange(false);
      router.push(`/`);
      setText("");
      setUrl("");
      void job;
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        const id = e.problem?.existing_job_id;
        setExisting(typeof id === "string" ? id : null);
        setError("This job description was already added.");
      } else {
        setError(e instanceof ApiError ? e.message : "Could not add the job.");
      }
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Add a job</DialogTitle>
        </DialogHeader>
        <Tabs value={mode} onValueChange={(v) => setMode(v as "paste" | "url")}>
          <TabsList>
            <TabsTrigger value="paste">Paste</TabsTrigger>
            <TabsTrigger value="url">URL</TabsTrigger>
          </TabsList>
          <TabsContent value="paste" className="space-y-1">
            <Label htmlFor="jd">Job description</Label>
            <Textarea id="jd" rows={10} value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste the full posting" />
          </TabsContent>
          <TabsContent value="url" className="space-y-1">
            <Label htmlFor="url">Posting URL</Label>
            <Input id="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" />
          </TabsContent>
        </Tabs>
        <div className="grid grid-cols-3 gap-2">
          <div className="space-y-1">
            <Label htmlFor="company">Company</Label>
            <Input id="company" value={company} onChange={(e) => setCompany(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="title">Title</Label>
            <Input id="title" value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="location">Location</Label>
            <Input id="location" value={location} onChange={(e) => setLocation(e.target.value)} />
          </div>
        </div>
        {error ? (
          <p role="alert" className="text-sm text-red-700">
            {error}{" "}
            {existing ? (
              <a className="underline" href={`/#${existing}`}>
                Show it
              </a>
            ) : null}
          </p>
        ) : null}
        <div className="flex justify-end">
          <Button onClick={submit} disabled={create.isPending}>
            Add job
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
