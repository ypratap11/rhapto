"use client";

import { Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AnswersTab } from "@/components/profile/AnswersTab";
import { BasesTab } from "@/components/profile/BasesTab";
import { BlocksTab } from "@/components/profile/BlocksTab";
import { GuardrailsTab } from "@/components/profile/GuardrailsTab";
import { ProfileSummaryCard, type ProfileCardId } from "@/components/profile/ProfileSummaryCard";
import { ResumeDocumentTab } from "@/components/profile/ResumeDocumentTab";
import { TracksTab } from "@/components/profile/TracksTab";
import { WatchlistTab } from "@/components/profile/WatchlistTab";
import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import { Breadcrumbs } from "@/components/shell/Breadcrumbs";
import { HeroBand } from "@/components/shell/HeroBand";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useAnswers,
  useBases,
  useDashboard,
  useGuardrails,
  useResumeDocument,
  useTracks,
  useWatchlist,
} from "@/lib/api/queries";
import { formatRelative } from "@/lib/format";

type Card = { id: ProfileCardId; title: string };

// Left column: building the resume. Right column: everything else Rhapto needs to know about you.
const LEFT_COLUMN: Card[] = [
  { id: "resume-template", title: "Resume template" },
  { id: "tracks", title: "Tracks" },
  { id: "blocks", title: "Blocks" },
  { id: "bases", title: "Bases" },
];
const RIGHT_COLUMN: Card[] = [
  { id: "answers", title: "Contact and answers" },
  { id: "guardrails", title: "Guardrails" },
  { id: "location", title: "Location preferences" },
  { id: "watchlist", title: "Watchlist" },
];

const ALL_CARD_IDS: ProfileCardId[] = [...LEFT_COLUMN, ...RIGHT_COLUMN].map((c) => c.id);

function isProfileCardId(value: string | null): value is ProfileCardId {
  return value !== null && (ALL_CARD_IDS as string[]).includes(value);
}

/** A query result shaped like TanStack's `UseQueryResult` — just the four fields every card
 * summary below gates its rendering on. */
type QueryState<T> = { data: T | undefined; isLoading: boolean; error: unknown; isPaused: boolean };

/**
 * One card summary line, covering the four states every query in this file can be in:
 * - loading: a shape-matched skeleton, never the empty-state text
 * - failed with nothing cached: a short "couldn't load" line, not a blank card
 * - failed with cached data (a paused or errored background refetch): the cached content stays,
 *   with a small inline note rather than being discarded
 * - settled with data: `render(data)` decides between "genuinely empty" and real content
 */
function CardSummary<T>({ query, render }: { query: QueryState<T>; render: (data: T) => React.ReactNode }) {
  if (query.isLoading) return <Skeleton className="h-4 w-40" />;
  const hasIssue = Boolean(query.error) || query.isPaused;
  if (query.data === undefined) {
    return <span className={hasIssue ? "text-fit-mid" : "text-muted-foreground"}>{hasIssue ? "Couldn’t load." : "Nothing here yet."}</span>;
  }
  return (
    <>
      {render(query.data)}
      {hasIssue ? <span className="ml-1.5 text-xs text-fit-mid">(refresh failed)</span> : null}
    </>
  );
}

function ProfilePageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  // `openCard` is derived straight from `searchParams` on every render, the same way Jobs derives
  // `currentPage` (src/app/jobs/page.tsx) — not mirrored into local state. That is what makes
  // `?card=` genuinely addressable rather than a one-time initial value: a shared `?card=guardrails`
  // link opens straight to that sheet, and Back closes an open sheet instead of leaving the page,
  // because `setOpenCard` below pushes a new history entry rather than replacing the current one.
  const rawCard = searchParams.get("card");
  const openCard: ProfileCardId | null = isProfileCardId(rawCard) ? rawCard : null;

  function setOpenCard(open: boolean, id: ProfileCardId) {
    const next = new URLSearchParams(searchParams.toString());
    if (open) next.set("card", id);
    else next.delete("card");
    router.push(`/profile${next.toString() ? `?${next.toString()}` : ""}`);
  }

  const answers = useAnswers();
  const dashboard = useDashboard();
  const tracks = useTracks();
  const bases = useBases();
  const guardrails = useGuardrails();
  const watchlist = useWatchlist();
  const resumeDocument = useResumeDocument();

  const checklist = dashboard.data?.checklist ?? null;

  const heroLoading = answers.isLoading || dashboard.isLoading;
  const heroIssue = Boolean(answers.error) || answers.isPaused || Boolean(dashboard.error) || dashboard.isPaused;
  const heroNothingToShow = !answers.data && !checklist && heroIssue;

  const cardContent: Record<ProfileCardId, React.ReactNode> = {
    "resume-template": <ResumeDocumentTab />,
    tracks: <TracksTab />,
    blocks: <BlocksTab />,
    bases: <BasesTab />,
    answers: <AnswersTab />,
    guardrails: <GuardrailsTab />,
    // The location answers (location_home, location_preferred, remote_ok) live in Answers — there
    // is no separate location editor.
    location: <AnswersTab />,
    watchlist: <WatchlistTab />,
  };

  const cardSummary: Record<ProfileCardId, React.ReactNode> = {
    "resume-template": (
      <CardSummary
        query={resumeDocument}
        render={(doc) => (doc ? `${doc.filename} · uploaded ${formatRelative(doc.uploaded_at)}` : "No resume uploaded yet.")}
      />
    ),
    tracks: (
      <CardSummary
        query={tracks}
        render={(rows) => (rows.length === 0 ? "No tracks yet. Pick a field and a role." : `${rows.length} track${rows.length === 1 ? "" : "s"}: ${rows.map((t) => t.name).join(", ")}`)}
      />
    ),
    blocks: (
      <CardSummary
        query={dashboard}
        render={(d) => `${d.checklist.verified_blocks} of ${d.checklist.total_blocks} blocks verified`}
      />
    ),
    bases: (
      <CardSummary
        query={bases}
        render={(rows) => (rows.length === 0 ? "No resume bases yet." : `${rows.length} resume base${rows.length === 1 ? "" : "s"}`)}
      />
    ),
    answers: (
      <CardSummary
        query={answers}
        render={(a) => (checklist?.contact_answers ? (a.name ?? "Complete") : "Add your name, email, phone and location.")}
      />
    ),
    guardrails: (
      <CardSummary
        query={guardrails}
        render={(rows) => {
          const active = rows.filter((r) => r.active).length;
          return rows.length === 0 ? "Using Rhapto's default guardrails." : `${active} of ${rows.length} rule${rows.length === 1 ? "" : "s"} active`;
        }}
      />
    ),
    location: (
      <CardSummary
        query={answers}
        render={(a) => {
          const preferredCount = (a.location_preferred ?? "").split(",").map((s) => s.trim()).filter(Boolean).length;
          const remote = a.remote_ok === "yes" ? "remote OK" : a.remote_ok ? `remote: ${a.remote_ok}` : "remote not set";
          return `${a.location_home ?? "Home not set"} · ${preferredCount} preferred area${preferredCount === 1 ? "" : "s"} · ${remote}`;
        }}
      />
    ),
    watchlist: (
      <CardSummary
        query={watchlist}
        render={(rows) => (rows.length === 0 ? "No companies on your watchlist yet." : `${rows.length} compan${rows.length === 1 ? "y" : "ies"} watched`)}
      />
    ),
  };

  function renderCard(card: Card) {
    return (
      <ProfileSummaryCard
        key={card.id}
        id={card.id}
        title={card.title}
        summary={cardSummary[card.id]}
        open={openCard === card.id}
        onOpenChange={(open) => setOpenCard(open, card.id)}
      >
        {cardContent[card.id]}
      </ProfileSummaryCard>
    );
  }

  return (
    <>
      <HeroBand tone="sand">
        {heroLoading ? (
          <div aria-hidden="true" className="space-y-2">
            <Skeleton className="h-8 w-64" />
            <Skeleton className="h-4 w-80" />
          </div>
        ) : heroNothingToShow ? (
          <>
            <h1 className="font-serif text-2xl font-medium">Your profile</h1>
            <p className="text-sm text-muted-foreground">Couldn&rsquo;t load your profile summary right now.</p>
          </>
        ) : (
          <>
            <h1 className="font-serif text-2xl font-medium">{answers.data?.name ?? "Your profile"}</h1>
            <p className="text-sm text-muted-foreground">
              {answers.data?.location_home ?? "Location not set"} · {checklist?.verified_blocks ?? 0} of {checklist?.total_blocks ?? 0} blocks verified
            </p>
          </>
        )}
      </HeroBand>
      <Breadcrumbs items={[{ label: "Profile" }]} />
      {heroIssue && !heroNothingToShow ? (
        <div className="mb-6">
          <ApiErrorBanner error={answers.error ?? dashboard.error ?? "Can't reach Rhapto's API."} />
        </div>
      ) : null}
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-6">{LEFT_COLUMN.map(renderCard)}</div>
        <div className="space-y-6">{RIGHT_COLUMN.map(renderCard)}</div>
      </div>
    </>
  );
}

export default function ProfilePage() {
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <ProfilePageInner />
    </Suspense>
  );
}
