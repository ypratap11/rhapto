import createClient, { type ClientOptions } from "openapi-fetch";
import type { paths } from "./schema";

export const STORAGE_KEYS = { token: "rhapto.token", apiUrl: "rhapto.apiUrl" } as const;
export const DEFAULT_API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, "") || "http://localhost:8000";

export type ConnectionSettings = { token: string; apiUrl: string };

export type Problem = { type?: string; title: string; status: number; detail?: string; [key: string]: unknown };

export class ApiError extends Error {
  status: number;
  problem: Problem | null;
  constructor(status: number, problem: Problem | null, fallback: string) {
    super(problem?.detail ?? problem?.title ?? fallback);
    this.name = "ApiError";
    this.status = status;
    this.problem = problem;
  }
}

function storage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

export function getSettings(): ConnectionSettings {
  const s = storage();
  const apiUrl = (s?.getItem(STORAGE_KEYS.apiUrl) || DEFAULT_API_URL).replace(/\/+$/, "");
  return { token: s?.getItem(STORAGE_KEYS.token) ?? "", apiUrl };
}

export function setSettings(settings: ConnectionSettings): void {
  const s = storage();
  if (!s) return;
  s.setItem(STORAGE_KEYS.token, settings.token.trim());
  s.setItem(STORAGE_KEYS.apiUrl, settings.apiUrl.trim().replace(/\/+$/, "") || DEFAULT_API_URL);
}

export function hasToken(): boolean {
  return getSettings().token.length > 0;
}

export function apiUrl(path: string): string {
  return `${getSettings().apiUrl}${path}`;
}

export function authHeaders(): Record<string, string> {
  const { token } = getSettings();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function apiClient(options: Partial<ClientOptions> = {}) {
  const { apiUrl: baseUrl } = getSettings();
  return createClient<paths>({ baseUrl, headers: authHeaders(), ...options });
}

type FetchResult<T> = { data?: T; error?: unknown; response: Response };

export async function unwrap<T>(promise: Promise<FetchResult<T>>): Promise<T> {
  const { data, error, response } = await promise;
  if (response.ok && data !== undefined) return data;
  if (response.ok) return undefined as T; // 204
  const problem = error && typeof error === "object" && "status" in (error as object) ? (error as Problem) : null;
  throw new ApiError(response.status, problem, `HTTP ${response.status}`);
}
