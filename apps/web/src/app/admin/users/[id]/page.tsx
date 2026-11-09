"use client";

import Link from "next/link";
import { use } from "react";
import { UserPanel } from "@/components/admin/UserPanel";

export default function AdminUserPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-4 px-4 py-6">
      <Link href="/admin" className="inline-flex min-h-11 items-center text-sm text-primary underline-offset-4 hover:underline">
        Back to admin
      </Link>
      <UserPanel userId={id} />
    </div>
  );
}
