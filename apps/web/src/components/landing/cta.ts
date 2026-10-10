/** The homepage's one primary call to action, shared by the hero and the tour so they cannot drift.
 * Hosted (same-origin, invite-only): the coach at /start. Self-hosted: Settings, to add a key. */
export function primaryCta(hosted: boolean): { href: string; label: string } {
  return hosted ? { href: "/start", label: "Tailor my resume" } : { href: "/settings", label: "Get started" };
}
