"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { type QueryClient, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, apiClient, apiUrl, authHeaders, unwrap, type Problem } from "./client";
import type { components, paths } from "./schema";
import type { PerSource, SearchIn, SearchResult } from "./portal";
import { DEFAULT_SEARCH_STATE, toJobsQuery, toSearchBody, type SearchState } from "@/lib/search-state";

// Re-exported so a page that already imports from "@/lib/api/queries" doesn't also need
// "@/lib/api/portal" for the shapes these hooks return.
export type { DashboardOut, DashboardChecklist, DashboardSavedSearch, DueFollowup, PerSource, SearchBody, SearchIn, SearchOut, SearchResult, SourceSetting, TaxonomyField, TaxonomyOut, TaxonomyRole, TaxonomySuggestions } from "./portal";

export type Schemas = components["schemas"];
export type JobOut = Schemas["JobOut"];
export type JobCreate = Schemas["JobCreate"];
export type TaskOut = Schemas["TaskOut"];
export type TailorBody = Schemas["TailorBody"];
export type Track = Schemas["Track"];
export type MeOut = Schemas["MeOut"];
export type PollRunOut = Schemas["PollRunOut"];
export type SourceInfoOut = Schemas["SourceInfoOut"];

export type JobRegion = "preferred" | "us" | "any";
export type LocationTier = NonNullable<JobOut["location_tier"]>;

export type JobFilters = { search: string; track: string | null; tab: "new" | "tailored" | "low"; region: JobRegion; sort: "fit" | "newest" };

// Where a new queue starts: jobs you could actually take, without hiding the ones whose location
// the scorer could not read. Anywhere is one click away in the Region select.
export const DEFAULT_REGION: JobRegion = "us";

export const keys = {
  me: ["me"] as const,
  // New and Tailored share one cache entry: both fetch the same "fit" bucket from
  // the API and differ only in client-side filtering (see JobList.tsx), so keying
  // on the derived bucket avoids a refetch/skeleton flash when switching tabs.
  jobs: (f: JobFilters) => ["jobs", f.search, f.track, f.tab === "low" ? "low" : "fit", f.region, f.sort] as const,
  job: (id: string) => ["job", id] as const,
  task: (id: string) => ["task", id] as const,
  tracks: ["profile", "tracks"] as const,
};

export const discoveryKeys = {
  runs: ["discovery", "runs"] as const,
  sources: ["discovery", "sources"] as const,
};

export function invalidateJobs(queryClient: QueryClient): void {
  void queryClient.invalidateQueries({ queryKey: ["jobs"] });
  void queryClient.invalidateQueries({ queryKey: ["job"] });
  // Hiding/unhiding a job changes new_fit_count and the saved-search "N new" badges.
  void queryClient.invalidateQueries({ queryKey: portalKeys.dashboard });
  invalidatePackageList(queryClient);
}

export function invalidateDiscovery(queryClient: QueryClient): void {
  void queryClient.invalidateQueries({ queryKey: ["discovery"] });
  invalidateJobs(queryClient);
}

export function useMe() {
  return useQuery({ queryKey: keys.me, queryFn: () => unwrap(apiClient().GET("/api/v1/me")) });
}

export function useJobs(filters: JobFilters) {
  return useQuery({
    queryKey: keys.jobs(filters),
    queryFn: () =>
      unwrap(
        apiClient().GET("/api/v1/jobs", {
          params: {
            query: {
              ...(filters.search ? { search: filters.search } : {}),
              ...(filters.track ? { track: filters.track } : {}),
              bucket: filters.tab === "low" ? "low" : "fit",
              region: filters.region,
              sort: filters.sort,
            },
          },
        }),
      ),
  });
}

export function useDiscoveryRuns() {
  return useQuery({ queryKey: discoveryKeys.runs, queryFn: () => unwrap(apiClient().GET("/api/v1/discovery/runs")), staleTime: 30_000 });
}

export function useSources() {
  return useQuery({ queryKey: discoveryKeys.sources, queryFn: () => unwrap(apiClient().GET("/api/v1/discovery/sources")), staleTime: Infinity });
}

export function usePollNow() {
  return useMutation({ mutationFn: () => unwrap(apiClient().POST("/api/v1/discovery/poll")) });
}

export function useRescueJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => unwrap(apiClient().POST("/api/v1/jobs/{job_id}/rescue", { params: { path: { job_id: jobId } } })),
    onSuccess: () => invalidateJobs(queryClient),
  });
}

export function useJob(id: string) {
  return useQuery({
    queryKey: keys.job(id),
    queryFn: () => unwrap(apiClient().GET("/api/v1/jobs/{job_id}", { params: { path: { job_id: id } } })),
  });
}

export function useCreateJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: JobCreate) => unwrap(apiClient().POST("/api/v1/jobs", { body })),
    onSuccess: () => invalidateJobs(queryClient),
  });
}

export function useDeleteJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => unwrap(apiClient().DELETE("/api/v1/jobs/{job_id}", { params: { path: { job_id: id } } })),
    onSuccess: () => {
      invalidateJobs(queryClient);
      void queryClient.invalidateQueries({ queryKey: ["applications"] });
    },
  });
}

export function useTracks() {
  return useQuery({ queryKey: keys.tracks, queryFn: () => unwrap(apiClient().GET("/api/v1/profile/tracks")) });
}

export function useTailor() {
  return useMutation({
    mutationFn: ({ jobId, body }: { jobId: string; body: TailorBody }) =>
      unwrap(apiClient().POST("/api/v1/jobs/{job_id}/tailor", { params: { path: { job_id: jobId } }, body })),
  });
}

export function useTask(id: string | null, enabled = true) {
  return useQuery({
    queryKey: keys.task(id ?? ""),
    queryFn: () => unwrap(apiClient().GET("/api/v1/tasks/{task_id}", { params: { path: { task_id: id ?? "" } } })),
    enabled: enabled && id !== null,
  });
}

export type PackageOut = Schemas["PackageOut"];
export type PackageSummary = Schemas["PackageSummary"];
export type ResumeDocument = Schemas["ResumeDocument"];
export type ResumeBullet = Schemas["ResumeBullet"];
export type ResumeEntry = Schemas["ResumeEntry"];
export type ResumeSection = Schemas["ResumeSection"];
export type GuardrailReport = Schemas["GuardrailReport"];
export type Edit = Schemas["Edit"];
export type EditPatch = Schemas["EditPatch"];
export type Violation = Schemas["Violation"];
export type Block = Schemas["Block"];
export type ApplicationOut = Schemas["ApplicationOut"];
export type BoardOut = Schemas["BoardOut"];
export type ApplicationCreate = Schemas["ApplicationCreate"];
export type ApplicationPatch = Schemas["ApplicationPatch"];

export const packageKeys = {
  package: (id: string) => ["package", id] as const,
  packages: (jobId: string) => ["packages", jobId] as const,
  blocks: ["profile", "blocks"] as const,
  applications: ["applications"] as const,
};

export type PackageListItem = components["schemas"]["PackageListItem"];
// Spec §3.4's four tabs. "all" is gone: every row belongs to exactly one of these.
export type PackageListFilter = "review" | "ready" | "blocked" | "applied";

export const packageListKeys = {
  list: (filter: PackageListFilter) => ["package-list", filter] as const,
};

export const PACKAGE_LIST_PARAMS: Record<PackageListFilter, { status?: "draft" | "ready" | "blocked"; applied?: boolean; archived?: boolean }> = {
  review: { applied: false, status: "draft", archived: false },
  ready: { applied: false, status: "ready", archived: false },
  blocked: { status: "blocked", archived: false },
  applied: { applied: true },
};

export function usePackageList(filter: PackageListFilter) {
  return useQuery({
    queryKey: packageListKeys.list(filter),
    queryFn: () => unwrap(apiClient().GET("/api/v1/packages", { params: { query: PACKAGE_LIST_PARAMS[filter] } })),
    staleTime: 10_000,
  });
}

export function invalidatePackageList(queryClient: QueryClient): void {
  void queryClient.invalidateQueries({ queryKey: ["package-list"] });
}

export function invalidatePackages(queryClient: QueryClient, jobId: string): void {
  void queryClient.invalidateQueries({ queryKey: packageKeys.packages(jobId) });
  void queryClient.invalidateQueries({ queryKey: ["package"] });
  invalidatePackageList(queryClient);
  invalidateJobs(queryClient);
}

export function invalidateApplications(queryClient: QueryClient): void {
  void queryClient.invalidateQueries({ queryKey: packageKeys.applications });
  invalidatePackageList(queryClient);
  invalidateJobs(queryClient);
}

// `enabled` defaults to true for every existing caller (the review page always wants its package);
// the job page passes false until it knows the latest package is blocked, so it can call this hook
// unconditionally (Rules of Hooks) without firing a request for a package it will not show.
export function usePackage(id: string, enabled = true) {
  return useQuery({
    queryKey: packageKeys.package(id),
    queryFn: () => unwrap(apiClient().GET("/api/v1/packages/{package_id}", { params: { path: { package_id: id } } })),
    enabled: enabled && id !== "",
  });
}

export function usePackages(jobId: string) {
  return useQuery({ queryKey: packageKeys.packages(jobId), queryFn: () => unwrap(apiClient().GET("/api/v1/jobs/{job_id}/packages", { params: { path: { job_id: jobId } } })) });
}

/** Assumption A2: PATCH /packages/{id} {status:"ready"} is how a reviewed resume becomes Ready. */
export function useMarkPackageReady() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(apiClient().PATCH("/api/v1/packages/{package_id}", { params: { path: { package_id: id } }, body: { status: "ready" } })),
    onSuccess: (updated) => invalidatePackages(queryClient, updated.job_id),
  });
}

/** "Skip" on the job page (spec: DidYouApplyPrompt) — archives the draft so it leaves the review
 * queue and, together with hiding the job, gets it out of Recommended without deleting anything. */
export function useArchivePackage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => unwrap(apiClient().POST("/api/v1/packages/{package_id}/archive", { params: { path: { package_id: id } } })),
    onSuccess: () => {
      invalidatePackageList(queryClient);
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      void queryClient.invalidateQueries({ queryKey: portalKeys.dashboard });
    },
  });
}

export function useBlocks() {
  return useQuery({ queryKey: packageKeys.blocks, queryFn: () => unwrap(apiClient().GET("/api/v1/profile/blocks")) });
}

export function usePatchPackage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, resume }: { id: string; resume: ResumeDocument }) =>
      unwrap(apiClient().PATCH("/api/v1/packages/{package_id}", { params: { path: { package_id: id } }, body: { resume } })),
    onSuccess: (created) => {
      invalidatePackages(queryClient, created.job_id);
      invalidatePackageList(queryClient);
    },
  });
}

export function usePatchPackageEdits() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, edits }: { id: string; edits: EditPatch[] }) =>
      unwrap(apiClient().PATCH("/api/v1/packages/{package_id}", { params: { path: { package_id: id } }, body: { edits } })),
    onSuccess: (created) => {
      invalidatePackages(queryClient, created.job_id);
      invalidatePackageList(queryClient);
    },
  });
}

export function useApplications() {
  return useQuery({ queryKey: packageKeys.applications, queryFn: () => unwrap(apiClient().GET("/api/v1/applications")) });
}

export function useCreateApplication() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ApplicationCreate) => unwrap(apiClient().POST("/api/v1/applications", { body })),
    onSuccess: () => invalidateApplications(queryClient),
  });
}

export function usePatchApplication() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: ApplicationPatch }) =>
      unwrap(apiClient().PATCH("/api/v1/applications/{application_id}", { params: { path: { application_id: id } }, body })),
    onSuccess: () => invalidateApplications(queryClient),
  });
}

export function useMarkApplied() {
  const create = useCreateApplication();
  const patch = usePatchApplication();
  return {
    isPending: create.isPending || patch.isPending,
    async markApplied(job: Pick<JobOut, "id">, packageId: string, existing: { id: string } | null): Promise<void> {
      let id: string;
      if (existing) {
        id = existing.id;
      } else {
        try {
          id = (await create.mutateAsync({ job_id: job.id, package_id: packageId })).id;
        } catch (e) {
          if (e instanceof ApiError && e.status === 409 && typeof e.problem?.existing_application_id === "string") {
            id = e.problem.existing_application_id;
          } else {
            throw e;
          }
        }
      }
      await patch.mutateAsync({ id, body: { status: "applied" } });
    },
  };
}

export function useDeleteApplication() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => unwrap(apiClient().DELETE("/api/v1/applications/{application_id}", { params: { path: { application_id: id } } })),
    onSuccess: () => invalidateApplications(queryClient),
  });
}

export type ResumeBase = Schemas["ResumeBase"];
export type GuardrailRule = Schemas["GuardrailRule"];
export type WatchlistEntry = Schemas["WatchlistEntry"];
export type AggregatorEntry = Schemas["AggregatorEntry"];
export type ImportOut = Schemas["ImportOut"];
export type SourceDocument = Schemas["SourceDocument"];
export type DocParagraph = Schemas["DocParagraph"];
export type DocSection = Schemas["DocSection"];
export type ResumeDocumentOut = Schemas["ResumeDocumentOut"];

export const profileKeys = {
  bases: ["profile", "bases"] as const,
  guardrails: ["profile", "guardrails"] as const,
  answers: ["profile", "answers"] as const,
  watchlist: ["profile", "watchlist"] as const,
  aggregators: ["profile", "aggregators"] as const,
  resumeDocument: ["profile", "resume-document"] as const,
};

export function invalidateProfile(queryClient: QueryClient): void {
  void queryClient.invalidateQueries({ queryKey: ["profile"] });
}

export function useBases() {
  return useQuery({ queryKey: profileKeys.bases, queryFn: () => unwrap(apiClient().GET("/api/v1/profile/bases")) });
}
export function useGuardrails() {
  return useQuery({ queryKey: profileKeys.guardrails, queryFn: () => unwrap(apiClient().GET("/api/v1/profile/guardrails")) });
}
export function useAnswers() {
  return useQuery({ queryKey: profileKeys.answers, queryFn: () => unwrap(apiClient().GET("/api/v1/profile/answers")) });
}
export function useWatchlist() {
  return useQuery({ queryKey: profileKeys.watchlist, queryFn: () => unwrap(apiClient().GET("/api/v1/profile/watchlist")) });
}
export function useAggregators() {
  return useQuery({ queryKey: profileKeys.aggregators, queryFn: () => unwrap(apiClient().GET("/api/v1/profile/aggregators")) });
}

function useProfileMutation<TVars, TData = unknown>(fn: (vars: TVars) => Promise<TData>) {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => invalidateProfile(queryClient) });
}

export function usePutBlock() {
  return useProfileMutation((block: Block) => unwrap(apiClient().PUT("/api/v1/profile/blocks/{block_id}", { params: { path: { block_id: block.id } }, body: block })));
}
export function useDeleteBlock() {
  return useProfileMutation((id: string) => unwrap(apiClient().DELETE("/api/v1/profile/blocks/{block_id}", { params: { path: { block_id: id } } })));
}
export function usePutBase() {
  return useProfileMutation((base: ResumeBase) => unwrap(apiClient().PUT("/api/v1/profile/bases/{base_id}", { params: { path: { base_id: base.id } }, body: base })));
}
export function useDeleteBase() {
  return useProfileMutation((id: string) => unwrap(apiClient().DELETE("/api/v1/profile/bases/{base_id}", { params: { path: { base_id: id } } })));
}
export function usePutTrack() {
  return useProfileMutation((track: Track) => unwrap(apiClient().PUT("/api/v1/profile/tracks/{track_id}", { params: { path: { track_id: track.id } }, body: track })));
}
export function useDeleteTrack() {
  return useProfileMutation((id: string) => unwrap(apiClient().DELETE("/api/v1/profile/tracks/{track_id}", { params: { path: { track_id: id } } })));
}
export function usePutGuardrail() {
  return useProfileMutation((rule: GuardrailRule) => unwrap(apiClient().PUT("/api/v1/profile/guardrails/{rule}", { params: { path: { rule: rule.rule } }, body: rule })));
}
export function useDeleteGuardrail() {
  return useProfileMutation((rule: string) => unwrap(apiClient().DELETE("/api/v1/profile/guardrails/{rule}", { params: { path: { rule } } })));
}
export function usePutAnswers() {
  return useProfileMutation((answers: Record<string, string>) => unwrap(apiClient().PUT("/api/v1/profile/answers", { body: answers })));
}
export function usePutWatchlist() {
  return useProfileMutation((entries: WatchlistEntry[]) => unwrap(apiClient().PUT("/api/v1/profile/watchlist", { body: entries })));
}
export function usePutAggregators() {
  return useProfileMutation<AggregatorEntry[], AggregatorEntry[]>((entries) => unwrap(apiClient().PUT("/api/v1/profile/aggregators", { body: entries })));
}
export function useImportProfile() {
  return useProfileMutation(async (files: File[]) => {
    const form = new FormData();
    for (const f of files) form.append("files", f, f.name);
    const response = await fetch(apiUrl("/api/v1/profile/import"), { method: "POST", body: form, headers: authHeaders() });
    if (!response.ok) {
      let problem: Problem | null = null;
      try {
        problem = (await response.json()) as Problem;
      } catch {
        problem = null;
      }
      throw new ApiError(response.status, problem, `HTTP ${response.status}`);
    }
    return (await response.json()) as ImportOut;
  });
}

export function useResumeDocument() {
  return useQuery({
    queryKey: profileKeys.resumeDocument,
    queryFn: async (): Promise<ResumeDocumentOut | null> => {
      try {
        return await unwrap(apiClient().GET("/api/v1/profile/resume-document"));
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null;
        throw e;
      }
    },
  });
}

export function useUploadResumeDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (file: File): Promise<ResumeDocumentOut> => {
      const form = new FormData();
      form.append("file", file, file.name);
      const response = await fetch(apiUrl("/api/v1/profile/resume-document"), { method: "POST", body: form, headers: authHeaders() });
      if (!response.ok) {
        let problem: Problem | null = null;
        try {
          problem = (await response.json()) as Problem;
        } catch {
          problem = null;
        }
        throw new ApiError(response.status, problem, `HTTP ${response.status}`);
      }
      return (await response.json()) as ResumeDocumentOut;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: profileKeys.resumeDocument });
    },
  });
}

export function useDeleteResumeDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(apiClient().DELETE("/api/v1/profile/resume-document")),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: profileKeys.resumeDocument });
    },
  });
}

export type LlmSettingsIn = Schemas["LlmSettingsIn"];
export type LlmSettingsOut = Schemas["LlmSettingsOut"];
export type LlmTestIn = Schemas["LlmTestIn"];
export type LlmTestOut = Schemas["LlmTestOut"];
export type ProviderInfoOut = Schemas["ProviderInfoOut"];

export const settingsKeys = {
  llm: ["settings", "llm"] as const,
};

/**
 * What `GET /settings/llm` told us. A 409 `llm_key_unreadable` (the stored key cannot be
 * decrypted, e.g. after the server secret rotated) is a state the user can fix by re-entering a
 * key, so it is data here rather than a query error: the Settings section still has to render its
 * form. Every other failure stays a real query error.
 *
 * That 409 carries `providers` for exactly this reason — it replaces the 200 that normally holds
 * the list, and without it the web app would need its own copy of the API's provider registry to
 * render the picker on the one screen that needs it most.
 */
export type LlmSettingsState =
  | { kind: "ok"; settings: LlmSettingsOut }
  | { kind: "unreadable"; detail: string; providers: ProviderInfoOut[] };

/** The `providers` array off a problem body, or [] when an older API did not send one. */
function problemProviders(problem: Problem | null): ProviderInfoOut[] {
  const providers = problem?.providers;
  return Array.isArray(providers) ? (providers as ProviderInfoOut[]) : [];
}

function invalidateLlmSettings(queryClient: QueryClient): void {
  void queryClient.invalidateQueries({ queryKey: settingsKeys.llm });
  // The Tailor buttons gate on /me's llm_configured, so it has to follow a save or a clear.
  void queryClient.invalidateQueries({ queryKey: keys.me });
}

export function useLlmSettings() {
  return useQuery({
    queryKey: settingsKeys.llm,
    queryFn: async (): Promise<LlmSettingsState> => {
      try {
        return { kind: "ok", settings: await unwrap(apiClient().GET("/api/v1/settings/llm")) };
      } catch (e) {
        if (e instanceof ApiError && e.status === 409 && e.problem?.code === "llm_key_unreadable") {
          return { kind: "unreadable", detail: e.message, providers: problemProviders(e.problem) };
        }
        throw e;
      }
    },
  });
}

export function useSaveLlmSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: LlmSettingsIn) => unwrap(apiClient().PUT("/api/v1/settings/llm", { body })),
    onSuccess: () => invalidateLlmSettings(queryClient),
  });
}

export function useTestLlm() {
  return useMutation({ mutationFn: (body: LlmTestIn) => unwrap(apiClient().POST("/api/v1/settings/llm/test", { body })) });
}

export function useDeleteLlmSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(apiClient().DELETE("/api/v1/settings/llm")),
    onSuccess: () => invalidateLlmSettings(queryClient),
  });
}

// --- Portal: live market search, saved searches, dashboard, taxonomy, source settings ---

export const portalKeys = {
  dashboard: ["dashboard"] as const,
  searches: ["searches"] as const,
  taxonomy: ["taxonomy"] as const,
  suggestions: ["taxonomy", "suggestions"] as const,
  sourceSettings: ["settings", "sources"] as const,
  jobsQuery: (s: SearchState, ids?: string[]) => ["jobs", "query", toJobsQuery(s, ids)] as const,
  // Prefixed with "jobs" (like jobsQuery above), not "dashboard": hiding or unhiding a job should
  // drop it from the recommendations too, and invalidateJobs already invalidates every ["jobs", ...]
  // key by prefix. One cache entry for all five pages — see useRecommendedJobs for why.
  recommended: ["jobs", "recommended"] as const,
};

export const LIVE_SEARCH_INTERVAL_MS = 3000;
export const LIVE_SEARCH_TIMEOUT_MS = 60_000;

export type LiveSearchStatus = "idle" | "searching" | "scoring" | "done" | "error";

/**
 * `GET /jobs` types `sort`/`hidden`/etc. as their native enum/boolean, but `toJobsQuery` returns the
 * comma-joined `Record<string, string>` the API actually reads off the query string — openapi-fetch
 * just stringifies whatever it's given, so this bridges the two without lying about the shape either
 * side really has.
 */
type JobsQueryParams = NonNullable<paths["/api/v1/jobs"]["get"]["parameters"]["query"]>;
function asJobsQuery(q: Record<string, string>): JobsQueryParams {
  return q as unknown as JobsQueryParams;
}

/**
 * Spec §6: the search returns immediately, known jobs already scored and new ones with
 * `best_fit: null`. Rather than block the grid on the worker, show every job at once and refetch
 * just the returned ids every 3s until nothing is unscored — or until 60s have passed, after
 * which an unscored job simply keeps its dashed ring.
 */
export function useLiveSearch(options: { intervalMs?: number; timeoutMs?: number } = {}) {
  const intervalMs = options.intervalMs ?? LIVE_SEARCH_INTERVAL_MS;
  const timeoutMs = options.timeoutMs ?? LIVE_SEARCH_TIMEOUT_MS;
  const [jobs, setJobs] = useState<JobOut[]>([]);
  const [perSource, setPerSource] = useState<PerSource | null>(null);
  const [status, setStatus] = useState<LiveSearchStatus>("idle");
  const [error, setError] = useState<unknown>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const deadline = useRef(0);
  const ids = useRef<string[]>([]);
  // Bumped by every run() call and by unmount, so an async continuation from an old run (its POST or
  // a poll GET still in flight) can tell it's been superseded before it touches state or starts an
  // interval — the component may already be gone, or a newer run() may already own `timer.current`.
  const generation = useRef(0);

  const stop = useCallback(() => {
    if (timer.current !== null) clearInterval(timer.current);
    timer.current = null;
  }, []);

  useEffect(
    () => () => {
      generation.current += 1;
      stop();
    },
    [stop],
  );

  const run = useCallback(
    (state: SearchState) => {
      const myGeneration = (generation.current += 1);
      stop();
      setStatus("searching");
      setError(null);
      void (async () => {
        try {
          const result: SearchResult = await unwrap(apiClient().POST("/api/v1/search", { body: toSearchBody(state) }));
          if (generation.current !== myGeneration) return; // unmounted, or superseded by a later run(), while this POST was in flight
          setJobs(result.jobs);
          setPerSource(result.per_source);
          ids.current = result.jobs.map((j) => j.id);
          if (result.jobs.every((j) => j.best_fit !== null)) {
            setStatus("done");
            return;
          }
          setStatus("scoring");
          deadline.current = Date.now() + timeoutMs;
          timer.current = setInterval(() => {
            void (async () => {
              try {
                const fresh = await unwrap(
                  apiClient().GET("/api/v1/jobs", { params: { query: asJobsQuery(toJobsQuery({ ...DEFAULT_SEARCH_STATE, sort: state.sort }, ids.current)) } }),
                );
                if (generation.current !== myGeneration) return;
                setJobs(fresh);
                if (fresh.every((j) => j.best_fit !== null) || Date.now() >= deadline.current) {
                  stop();
                  setStatus("done");
                }
              } catch (e) {
                if (generation.current !== myGeneration) return;
                stop();
                setError(e);
                setStatus("error");
              }
            })();
          }, intervalMs);
        } catch (e) {
          if (generation.current !== myGeneration) return;
          setError(e);
          setStatus("error");
        }
      })();
    },
    [intervalMs, stop, timeoutMs],
  );

  return { run, jobs, perSource, status, error };
}

/**
 * `searchId` is a `?search_id=` param carried over from the Dashboard's saved-search rail: it
 * asks the API to scope results to that saved search rather than (or alongside) `state`'s own
 * filters. It rides in as an extra query param next to whatever `toJobsQuery(state)` already
 * produced, so `SearchState` itself never needs to know about it.
 */
export function useJobsQuery(state: SearchState, options: { enabled?: boolean; searchId?: string | null } = {}) {
  const searchId = options.searchId ?? null;
  return useQuery({
    queryKey: [...portalKeys.jobsQuery(state), searchId] as const,
    queryFn: () =>
      unwrap(
        apiClient().GET("/api/v1/jobs", {
          params: { query: asJobsQuery({ ...toJobsQuery(state), ...(searchId ? { search_id: searchId } : {}) }) },
        }),
      ),
    enabled: options.enabled ?? true,
  });
}

export function useSavedSearches() {
  return useQuery({ queryKey: portalKeys.searches, queryFn: () => unwrap(apiClient().GET("/api/v1/searches")) });
}

export function useSaveSearch() {
  const queryClient = useQueryClient();
  return useMutation({
    // Assumption A9: POST /searches takes the form shape and names the search after the query.
    mutationFn: (state: SearchState) => {
      const body: SearchIn = {
        active: true,
        query: state.query.trim() || null,
        location: state.location.trim() || null,
        remote: state.remote,
      };
      return unwrap(apiClient().POST("/api/v1/searches", { body }));
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: portalKeys.searches });
      void queryClient.invalidateQueries({ queryKey: portalKeys.dashboard });
    },
  });
}

export function useDeleteSavedSearch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => unwrap(apiClient().DELETE("/api/v1/searches/{search_id}", { params: { path: { search_id: id } } })),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: portalKeys.searches }),
  });
}

export function useUpdateSavedSearch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: SearchIn }) =>
      unwrap(apiClient().PUT("/api/v1/searches/{search_id}", { params: { path: { search_id: id } }, body })),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: portalKeys.searches }),
  });
}

/** Opening a saved search's results is what clears its "N new" badge (spec §6). */
export function useMarkSearchViewed() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => unwrap(apiClient().POST("/api/v1/searches/{search_id}/viewed", { params: { path: { search_id: id } } })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: portalKeys.searches });
      void queryClient.invalidateQueries({ queryKey: portalKeys.dashboard });
    },
  });
}

export function useHideJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => unwrap(apiClient().POST("/api/v1/jobs/{job_id}/hide", { params: { path: { job_id: id } } })),
    onSuccess: () => invalidateJobs(queryClient),
  });
}

export function useUnhideJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => unwrap(apiClient().POST("/api/v1/jobs/{job_id}/unhide", { params: { path: { job_id: id } } })),
    onSuccess: () => invalidateJobs(queryClient),
  });
}

export function useSourceSettings() {
  return useQuery({ queryKey: portalKeys.sourceSettings, queryFn: () => unwrap(apiClient().GET("/api/v1/settings/sources")), staleTime: 60_000 });
}

/** Career fields and roles for the Field select (spec §5) — static enough per deploy to cache like source settings. */
export function useTaxonomy() {
  return useQuery({ queryKey: portalKeys.taxonomy, queryFn: () => unwrap(apiClient().GET("/api/v1/taxonomy")), staleTime: 60_000 });
}

/** The Dashboard's one call: both headline numbers, the checklist, due follow-ups and saved-search counts. */
export function useDashboard() {
  return useQuery({ queryKey: portalKeys.dashboard, queryFn: () => unwrap(apiClient().GET("/api/v1/dashboard")), staleTime: 30_000 });
}

export const RECOMMENDED_PAGE_SIZE = 10;
export const RECOMMENDED_MAX_PAGES = 5;

/**
 * Spec §3.1: fit-ranked jobs with no resume and no application, ten per page, up to five pages. The
 * server applies the "no package, no application, not hidden, not unlisted" filter (assumption A8)
 * via `recommended=true`; the client pages.
 *
 * `GET /jobs` has no `limit`/`offset` (schema.d.ts's `list_jobs_api_v1_jobs_get` query only has
 * search/track/bucket/region/sort/ids/hidden/search_id/posted_within/sources/field/recommended), so
 * this takes the client-side path the brief allows: fetch the whole recommended set once and slice
 * it into pages here.
 */
export function useRecommendedJobs(page: number) {
  const query = useQuery({
    queryKey: portalKeys.recommended,
    queryFn: () => unwrap(apiClient().GET("/api/v1/jobs", { params: { query: { recommended: true, sort: "fit" } } })),
    staleTime: 30_000,
  });
  const all = query.data ?? [];
  return { ...query, data: all.slice(page * RECOMMENDED_PAGE_SIZE, page * RECOMMENDED_PAGE_SIZE + RECOMMENDED_PAGE_SIZE) };
}
