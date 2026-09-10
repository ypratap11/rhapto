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
