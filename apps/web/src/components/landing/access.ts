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
