"use client";

import { Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { AddJobDialog } from "@/components/queue/AddJobDialog";
import { JobList } from "@/components/queue/JobList";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function QueuePage() {
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setSearch(query.trim()), 250);
    return () => clearTimeout(t);
  }, [query]);
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl">Queue</h1>
        <div className="flex gap-2">
          <Input aria-label="Search jobs" placeholder="Search company, title, text" value={query} onChange={(e) => setQuery(e.target.value)} className="w-64" />
          <Button onClick={() => setOpen(true)}>
            <Plus className="size-4" aria-hidden /> Add job
          </Button>
        </div>
      </div>
      <JobList search={search} />
      <AddJobDialog open={open} onOpenChange={setOpen} />
    </div>
  );
}
