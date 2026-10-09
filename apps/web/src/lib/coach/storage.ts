import type { ResumeImportOut } from "@/lib/api/queries";

/** All the coach keeps of an import: the proposed tracks and the location. Never the blocks (the coach
 * saves none) and never any resume text. */
export type CachedProposal = Pick<ResumeImportOut, "tracks" | "location">;

const proposalKey = (userId: string) => `rhapto.coach.proposal.${userId}`;
const trackKey = (userId: string) => `rhapto.coach.track.${userId}`;

function area(kind: "session" | "local"): Storage | null {
  try {
    return typeof window === "undefined" ? null : kind === "session" ? window.sessionStorage : window.localStorage;
  } catch {
    return null;
  }
}

export function readProposal(userId: string): CachedProposal | null {
  try {
    const raw = area("session")?.getItem(proposalKey(userId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<CachedProposal>;
    return Array.isArray(parsed.tracks) && parsed.location ? { tracks: parsed.tracks, location: parsed.location } : null;
  } catch {
    return null;
  }
}

export function writeProposal(userId: string, proposal: CachedProposal): void {
  try {
    area("session")?.setItem(proposalKey(userId), JSON.stringify({ tracks: proposal.tracks, location: proposal.location }));
  } catch {
    /* storage blocked: the coach just cannot resume between steps 1 and 2 */
  }
}

export function clearProposal(userId: string): void {
  try {
    area("session")?.removeItem(proposalKey(userId));
  } catch {
    /* nothing to clear */
  }
}

export function readConfirmedTrack(userId: string): string | null {
  try {
    return area("local")?.getItem(trackKey(userId)) ?? null;
  } catch {
    return null;
  }
}

export function writeConfirmedTrack(userId: string, trackId: string): void {
  try {
    area("local")?.setItem(trackKey(userId), trackId);
  } catch {
    /* falls back to tracks[0] */
  }
}
