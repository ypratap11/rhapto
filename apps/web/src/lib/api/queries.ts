"use client";

import { type QueryClient, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient, unwrap } from "./client";
import type { components } from "./schema";

export type Schemas = components["schemas"];
export type JobOut = Schemas["JobOut"];
export type JobCreate = Schemas["JobCreate"];
export type TaskOut = Schemas["TaskOut"];
export type TailorBody = Schemas["TailorBody"];
export type Track = Schemas["Track"];
export type MeOut = Schemas["MeOut"];

export const keys = {
  me: ["me"] as const,
  jobs: (search: string) => ["jobs", search] as const,
  job: (id: string) => ["job", id] as const,
  task: (id: string) => ["task", id] as const,
  tracks: ["profile", "tracks"] as const,
};

export function invalidateJobs(queryClient: QueryClient): void {
  void queryClient.invalidateQueries({ queryKey: ["jobs"] });
  void queryClient.invalidateQueries({ queryKey: ["job"] });
}

export function useMe() {
  return useQuery({ queryKey: keys.me, queryFn: () => unwrap(apiClient().GET("/api/v1/me")) });
}

export function useJobs(search: string) {
  return useQuery({
    queryKey: keys.jobs(search),
    queryFn: () => unwrap(apiClient().GET("/api/v1/jobs", { params: { query: search ? { search } : {} } })),
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
    onSuccess: () => invalidateJobs(queryClient),
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
