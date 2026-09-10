"use client";

import { useRouter } from "next/navigation";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { PackageOut } from "@/lib/api/queries";

export function VersionSwitcher({ jobId, packages, currentId }: { jobId: string; packages: PackageOut[]; currentId: string }) {
  const router = useRouter();
  return (
    <Select value={currentId} onValueChange={(id: string | null) => id && router.push(`/jobs/${jobId}/packages/${id}`)}>
      <SelectTrigger className="w-48" aria-label="Package version">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {packages.map((p) => (
          <SelectItem key={p.id} value={p.id}>
            v{p.version} · {p.status}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
