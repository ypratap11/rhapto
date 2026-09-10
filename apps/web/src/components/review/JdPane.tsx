import type { JobOut } from "@/lib/api/queries";
import { highlightTerms } from "@/lib/highlight";

export function JdPane({ job }: { job: JobOut }) {
  const extract = job.extracted;
  const terms = extract ? [...extract.must_have, ...extract.keywords] : [];
  const segments = highlightTerms(job.jd_text, terms);
  return (
    <aside className="space-y-4 rounded-md border border-border bg-card p-6">
      <div>
        <h2 className="text-lg">{job.title ?? "Job description"}</h2>
        <p className="text-sm text-muted-foreground">{[job.company, job.location].filter(Boolean).join(" · ")}</p>
      </div>
      {extract ? (
        <div className="space-y-2 text-sm">
          <p>
            <span className="font-medium">Must have:</span> {extract.must_have.join("; ") || "none listed"}
          </p>
          <p>
            <span className="font-medium">Nice to have:</span> {extract.nice_to_have.join("; ") || "none listed"}
          </p>
          <p className="text-muted-foreground">
            {extract.location_policy} · {extract.seniority}
          </p>
        </div>
      ) : null}
      <p className="whitespace-pre-wrap text-sm leading-6">
        {segments.map((seg, i) => (seg.hit ? <mark key={i}>{seg.text}</mark> : <span key={i}>{seg.text}</span>))}
      </p>
    </aside>
  );
}
