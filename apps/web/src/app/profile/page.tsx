"use client";

import { Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AnswersTab } from "@/components/profile/AnswersTab";
import { BasesTab } from "@/components/profile/BasesTab";
import { BlocksTab } from "@/components/profile/BlocksTab";
import { GuardrailsTab } from "@/components/profile/GuardrailsTab";
import { LocationTab } from "@/components/profile/LocationTab";
import { ProfileSummaryCard, type ProfileCardId } from "@/components/profile/ProfileSummaryCard";
import { ResumeDocumentTab } from "@/components/profile/ResumeDocumentTab";
import { TracksTab } from "@/components/profile/TracksTab";
import { WatchlistTab } from "@/components/profile/WatchlistTab";
import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import { Breadcrumbs } from "@/components/shell/Breadcrumbs";
import { PageHero } from "@/components/shell/PageHero";
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

type Card = { id: ProfileCardId; title: string; blurb: string };

// Left column: building the resume. Right column: everything else Rhapto needs to know about you.
const LEFT_COLUMN: Card[] = [
  { id: "resume-template", title: "Your resume file", blurb: "The resume you uploaded. Light touch rewords a few of its lines for each job." },
  { id: "tracks", title: "Roles you want", blurb: "The kinds of job Rhapto looks for and writes resumes for." },
  { id: "blocks", title: "Your experience", blurb: "The facts every resume line comes from." },
  { id: "bases", title: "Starting resumes", blurb: "The starting point Rhapto uses for each kind of role." },
];
const RIGHT_COLUMN: Card[] = [
  { id: "answers", title: "Contact details and saved answers", blurb: "Your name, email and phone, plus answers to common application questions." },
  {
    id: "guardrails",
    title: "Writing rules",
    blurb:
      "Rhapto checks every resume before you can download it: no number that is not already in your resume file or a confirmed item, and no line without a source. You can add extra checks here.",
  },
  { id: "location", title: "Where you want to work", blurb: "Your home town, the areas you would consider, and whether remote is fine." },
  { id: "watchlist", title: "Companies you follow", blurb: "Companies Rhapto checks for new jobs." },
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
  // link opens straight to that sheet.
  //
  // Open pushes a new history entry; close replaces the current one rather than pushing another.
  // A close is the undo of an open, not a fresh step — the same distinction Task 5b drew between
  // `goToPage` (push, an undoable step) and `updateState` (replace, a filter edit that shouldn't
  // spam history). Getting this backwards — pushing on close too — means Back from the closed state
  // lands back on the *open* entry and reopens the sheet the user just dismissed, the opposite of
  // what push-on-open was for. With push-on-open + replace-on-close: Back while a sheet is open
  // returns to the card-less URL and closes it; Back after an explicit close leaves the page.
  const rawCard = searchParams.get("card");
  const openCard: ProfileCardId | null = isProfileCardId(rawCard) ? rawCard : null;

  function setOpenCard(open: boolean, id: ProfileCardId) {
    const next = new URLSearchParams(searchParams.toString());
    if (open) next.set("card", id);
    else next.delete("card");
    const url = `/profile${next.toString() ? `?${next.toString()}` : ""}`;
    if (open) router.push(url);
    else router.replace(url);
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
    location: <LocationTab />,
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
        render={(rows) => (rows.length === 0 ? "No roles chosen yet. Pick a field and a role." : `${rows.length} role${rows.length === 1 ? "" : "s"}: ${rows.map((t) => t.name).join(", ")}`)}
      />
    ),
    blocks: (
      <CardSummary
        query={dashboard}
        render={(d) => `${d.checklist.verified_blocks} of ${d.checklist.total_blocks} items confirmed`}
      />
    ),
    bases: (
      <CardSummary
        query={bases}
        render={(rows) => (rows.length === 0 ? "No starting resumes yet." : `${rows.length} starting resume${rows.length === 1 ? "" : "s"}`)}
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
          const off = rows.filter((r) => !r.active).length;
          return off === 0 ? "Standard rules are on." : `${off} rule${off === 1 ? "" : "s"} turned off.`;
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
        render={(rows) => (rows.length === 0 ? "You are not following any companies yet." : `${rows.length} compan${rows.length === 1 ? "y" : "ies"} followed`)}
      />
    ),
  };

  function renderCard(card: Card) {
    return (
      <ProfileSummaryCard
        key={card.id}
        id={card.id}
        title={card.title}
        summary={
          <>
            <span className="block">{card.blurb}</span>
            <span className="mt-1.5 block font-medium text-foreground">{cardSummary[card.id]}</span>
          </>
        }
        open={openCard === card.id}
        onOpenChange={(open) => setOpenCard(open, card.id)}
        // The watchlist editor is a six-column table (company, source, board, keywords,
        // discovered, remove); in the default panel its inputs truncate to "Anthro"/"CoreW" and
        // everything past Board hides behind a horizontal scrollbar.
        wide={card.id === "watchlist"}
      >
        {cardContent[card.id]}
      </ProfileSummaryCard>
    );
  }

  return (
    <>
      <PageHero
        title={
          heroLoading ? (
            <>
              <span className="sr-only">Loading your profile</span>
              <Skeleton aria-hidden className="h-[1.15em] w-64 max-w-full" />
            </>
          ) : heroNothingToShow ? (
            "Your profile"
          ) : (
            (answers.data?.name ?? "Your profile")
          )
        }
        subtitle={
          heroLoading ? (
            <Skeleton aria-hidden className="h-6 w-80 max-w-full" />
          ) : heroNothingToShow ? (
            <>Couldn&rsquo;t load your profile summary right now.</>
          ) : (
            <>
              {answers.data?.location_home ?? "Location not set"} · {checklist?.verified_blocks ?? 0} of {checklist?.total_blocks ?? 0} items confirmed
            </>
          )
        }
      />
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
