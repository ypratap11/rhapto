/** Where "Request access" goes.
 *
 * Rhapto's hosted instance has no registration: access is a Cloudflare Access email allowlist the
 * maintainer edits by hand. So the way in for a stranger is to ask, and asking is an email. Kept in
 * its own module, with no `"use client"` and no React, so both the server-rendered `Landing` and any
 * client child can import it and changing the address stays a one-line edit.
 *
 * The forwarder for this address is configured in Cloudflare Email Routing, outside this repo; if it
 * is not yet in place the mail bounces rather than being silently dropped, which is why the page does
 * not promise that anyone will reply. */
export const ACCESS_REQUEST_EMAIL = "hellorhapto@augaster.com";

/** Subject only. A prefilled body would either be empty ceremony or would put words in the sender's
 * mouth about who they are, and nothing on this page knows who they are. */
export const ACCESS_REQUEST_MAILTO = `mailto:${ACCESS_REQUEST_EMAIL}?subject=${encodeURIComponent(
  "Rhapto access request",
)}`;

/** Where "Request beta access" goes (the owner's Google Form). Both `Landing` and the
 * tour's outro read it through `accessRequestLink`, so they cannot drift apart. Emptying it falls
 * back to the mailto above, which is the one-line way to switch back. */
export const ACCESS_REQUEST_URL = "https://forms.gle/1GUeGcKB9fCiJAdFA";

export type AccessRequestLink = {
  href: string;
  /** True only for an https URL: the caller opens it in a new tab with `rel="noreferrer"`. The mailto
   * fallback is not external and gets neither attribute. */
  external: boolean;
};

/** Pure. Anything that is not a parseable https URL (empty, http, javascript:, mailto:, garbage)
 * falls back to the mailto, so a typo in `ACCESS_REQUEST_URL` cannot produce a dead or unsafe link. */
export function accessRequestLink(url: string = ACCESS_REQUEST_URL): AccessRequestLink {
  try {
    if (new URL(url).protocol === "https:") return { href: url, external: true };
  } catch {
    // not a URL: fall through to the mailto
  }
  return { href: ACCESS_REQUEST_MAILTO, external: false };
}
