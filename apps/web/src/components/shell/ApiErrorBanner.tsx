import Link from "next/link";
import { ApiError } from "@/lib/api/client";

export function ApiErrorBanner({ error }: { error: unknown }) {
  if (!error) return null;
  const api = error instanceof ApiError ? error : null;
  const title = api?.problem?.title ?? "Request failed";
  const detail = api?.message ?? (error instanceof Error ? error.message : String(error));
  return (
    <div role="alert" className="rounded-md border border-fit-mid/40 bg-fit-mid-bg px-4 py-3 text-sm text-foreground">
      <strong>{title}.</strong> {detail}
      {api?.status === 401 ? (
        <>
          {" "}
          <Link href="/settings" className="underline">
            Check your token in Settings
          </Link>
          .
        </>
      ) : null}
    </div>
  );
}
