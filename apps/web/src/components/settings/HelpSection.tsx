import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type HelpDoc = { title: string; path: string; slug: string };

// The eight user-guide pages Task 13 is dispatched to write, one per portal area (the product's
// five tabs, plus getting-started, settings and an FAQ). This exact filename list is canonical —
// Task 13's own dispatch carries the same one, specifically so the two cannot drift apart again.
// Nothing here reads those files, so this list is safe to ship ahead of them existing.
const USER_GUIDE: HelpDoc[] = [
  { title: "Getting started", path: "docs/user-guide/getting-started.md", slug: "getting-started" },
  { title: "Your dashboard", path: "docs/user-guide/dashboard.md", slug: "dashboard" },
  { title: "Finding and searching jobs", path: "docs/user-guide/jobs-and-search.md", slug: "jobs-and-search" },
  { title: "Reviewing generated resumes", path: "docs/user-guide/resumes.md", slug: "resumes" },
  { title: "Tracking your pipeline", path: "docs/user-guide/pipeline.md", slug: "pipeline" },
  { title: "Your profile and tracks", path: "docs/user-guide/profile-and-tracks.md", slug: "profile-and-tracks" },
  { title: "Settings and job sources", path: "docs/user-guide/settings-and-sources.md", slug: "settings-and-sources" },
  { title: "Frequently asked questions", path: "docs/user-guide/faq.md", slug: "faq" },
];

// Existing docs in this checkout (see docs/ and docs/superpowers/specs/).
const PRODUCT_DOCS: HelpDoc[] = [
  { title: "Requirements & architecture", path: "docs/requirements-architecture.md", slug: "requirements-architecture" },
  { title: "Portal design spec", path: "docs/superpowers/specs/2026-09-14-portal-design.md", slug: "2026-09-14-portal-design" },
  { title: "Job portal design", path: "docs/superpowers/specs/2026-09-14-job-portal-design.md", slug: "2026-09-14-job-portal-design" },
  { title: "Guided flow design", path: "docs/superpowers/specs/2026-09-11-guided-flow-design.md", slug: "2026-09-11-guided-flow-design" },
  { title: "Tune mode design", path: "docs/superpowers/specs/2026-09-11-tune-mode-design.md", slug: "2026-09-11-tune-mode-design" },
  { title: "Portal backend follow-ups", path: "docs/portal-backend-followups.md", slug: "portal-backend-followups" },
];

function DocList({ heading, docs, docsBase }: { heading: string; docs: HelpDoc[]; docsBase: string | undefined }) {
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium text-muted-foreground">{heading}</h3>
      <ul className="space-y-1.5">
        {docs.map((doc) => (
          <li key={doc.slug} className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 text-sm">
            {docsBase ? (
              <a href={`${docsBase}/${doc.slug}.md`} target="_blank" rel="noreferrer" className="font-medium text-primary underline-offset-4 hover:underline">
                {doc.title}
              </a>
            ) : (
              <span className="font-medium">{doc.title}</span>
            )}
            <code className="font-mono text-xs text-muted-foreground">{doc.path}</code>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Assumption A12: this checkout has no git remote, so there's no default docs URL to invent —
 * titles stay plain text (with their on-disk path alongside) unless NEXT_PUBLIC_DOCS_URL is set. */
export function HelpSection() {
  const docsBase = process.env.NEXT_PUBLIC_DOCS_URL;
  return (
    <Card id="help" className="scroll-mt-20">
      <CardHeader>
        <CardTitle>Help</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <DocList heading="User guide" docs={USER_GUIDE} docsBase={docsBase} />
        <DocList heading="Product docs" docs={PRODUCT_DOCS} docsBase={docsBase} />
      </CardContent>
    </Card>
  );
}
