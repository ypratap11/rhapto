"use client";

import { useRouter } from "next/navigation";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { PackageOut } from "@/lib/api/queries";
import { PACKAGE_STATUS_LABEL } from "@/lib/status";

export function VersionSwitcher({ jobId, packages, currentId }: { jobId: string; packages: PackageOut[]; currentId: string }) {
  const router = useRouter();
  return (
    <Select value={currentId} onValueChange={(id: string | null) => id && router.push(`/jobs/${jobId}/packages/${id}`)}>
      <SelectTrigger className="w-48" aria-label="Resume version">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {packages.map((p) => (
          <SelectItem key={p.id} value={p.id}>
            Version {p.version} · {(PACKAGE_STATUS_LABEL as Record<string, string>)[p.status] ?? p.status}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
