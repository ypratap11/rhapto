"use client";

import { type QueryClient, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, apiClient, apiUrl, authHeaders, unwrap, type Problem } from "./client";
import type { components } from "./schema";

export type Schemas = components["schemas"];
export type JobOut = Schemas["JobOut"];
export type JobCreate = Schemas["JobCreate"];
export type TaskOut = Schemas["TaskOut"];
export type TailorBody = Schemas["TailorBody"];
export type Track = Schemas["Track"];
export type MeOut = Schemas["MeOut"];
export type PollRunOut = Schemas["PollRunOut"];
export type SourceInfoOut = Schemas["SourceInfoOut"];

export type JobFilters = { search: string; track: string | null; bucket: "fit" | "low"; sort: "fit" | "newest" };

export const keys = {
  me: ["me"] as const,
  jobs: (f: JobFilters) => ["jobs", f.search, f.track, f.bucket, f.sort] as const,
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
              bucket: filters.bucket,
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

export function invalidatePackages(queryClient: QueryClient, jobId: string): void {
  void queryClient.invalidateQueries({ queryKey: packageKeys.packages(jobId) });
  void queryClient.invalidateQueries({ queryKey: ["package"] });
  invalidateJobs(queryClient);
}

export function invalidateApplications(queryClient: QueryClient): void {
  void queryClient.invalidateQueries({ queryKey: packageKeys.applications });
  invalidateJobs(queryClient);
}

export function usePackage(id: string) {
  return useQuery({ queryKey: packageKeys.package(id), queryFn: () => unwrap(apiClient().GET("/api/v1/packages/{package_id}", { params: { path: { package_id: id } } })) });
}

export function usePackages(jobId: string) {
  return useQuery({ queryKey: packageKeys.packages(jobId), queryFn: () => unwrap(apiClient().GET("/api/v1/jobs/{job_id}/packages", { params: { path: { job_id: jobId } } })) });
}

export function useBlocks() {
  return useQuery({ queryKey: packageKeys.blocks, queryFn: () => unwrap(apiClient().GET("/api/v1/profile/blocks")) });
}

export function usePatchPackage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, resume }: { id: string; resume: ResumeDocument }) =>
      unwrap(apiClient().PATCH("/api/v1/packages/{package_id}", { params: { path: { package_id: id } }, body: { resume } })),
    onSuccess: (created) => invalidatePackages(queryClient, created.job_id),
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

export const profileKeys = {
  bases: ["profile", "bases"] as const,
  guardrails: ["profile", "guardrails"] as const,
  answers: ["profile", "answers"] as const,
  watchlist: ["profile", "watchlist"] as const,
  aggregators: ["profile", "aggregators"] as const,
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
