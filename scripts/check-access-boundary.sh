#!/usr/bin/env bash
# Verify the Cloudflare Access boundary: the marketing pages are public, everything that carries data
# is not.
#
#   scripts/check-access-boundary.sh
#   RHAPTO_HOST_URL=https://rhapto.augaster.com scripts/check-access-boundary.sh
#
# Run it with NO Access session — a fresh shell, never a browser you are logged into. It sends no
# cookies, so a 200 from a protected path means that path is genuinely open to the internet.
#
# The distinction that matters, and the reason this script exists rather than "click around and see":
# an unauthenticated request to an Access-PROTECTED path is answered by Cloudflare with a 302 to the
# team login domain, and the origin is never reached. A path that has been BYPASSED reaches the origin,
# and the origin answers — 200 for a page, 401 for the API. So a 401 from /api/v1/* is NOT a pass: it
# means Access let the request through and only the application refused it. That is one misconfigured
# allowlist away from being a data leak, and it is invisible if you only check "did I get in".
set -uo pipefail

HOST="${RHAPTO_HOST_URL:-https://rhapto.augaster.com}"

# Public: the product's own shop window. No session required, nothing user-specific rendered.
PUBLIC_PATHS=(/ /about)
# Protected: every path that renders or returns somebody's data.
PROTECTED_PATHS=(/jobs /pipeline /profile /resumes /settings /dashboard /api/v1/me /api/v1/dashboard /api/v1/jobs)

hdr="$(mktemp)"; body="$(mktemp)"
trap 'rm -f "$hdr" "$body"' EXIT

failures=0
note() { printf '  %s\n' "$*"; }

probe() { # $1 = path -> sets CODE and LOCATION
  CODE="$(curl -sS -o "$body" -D "$hdr" -w '%{http_code}' --max-time 20 "${HOST}$1" || echo 000)"
  LOCATION="$(tr -d '\r' < "$hdr" | awk 'tolower($1)=="location:"{print $2}' | tail -1)"
}

echo "==> Access boundary check against ${HOST}"
echo "    (sending no cookies; run this outside any logged-in session)"
echo

echo "PUBLIC — must reach the origin and render"
for p in "${PUBLIC_PATHS[@]}"; do
  probe "$p"
  if [[ "$CODE" == "200" ]]; then
    note "ok       $p -> 200"
  elif [[ "$LOCATION" == *cloudflareaccess.com* ]]; then
    note "FAIL     $p -> $CODE, redirected to Access. Still protected; the bypass does not cover it."
    failures=$((failures + 1))
  else
    note "FAIL     $p -> $CODE${LOCATION:+ (Location: $LOCATION)}"
    failures=$((failures + 1))
  fi
done

echo
echo "PUBLIC ASSETS — a styled page, not a bare-HTML one"
# Derived from the live page rather than hardcoded: Next fingerprints these filenames every build, and
# `next/font/google` self-hosts the fonts under /_next/static/media, so a blocked /_next/* renders the
# landing page unstyled with no fonts. That looks worse than a login screen, and a check with a
# hardcoded filename would silently stop testing anything the first time the app is rebuilt.
probe "/"
asset="$(grep -oE '/_next/static/[A-Za-z0-9._/-]+' "$body" | head -1)"
if [[ -z "$asset" ]]; then
  note "SKIP     no /_next/static reference found in / — cannot verify assets (did / return the app?)"
else
  probe "$asset"
  if [[ "$CODE" == "200" ]]; then
    note "ok       $asset -> 200"
  else
    note "FAIL     $asset -> $CODE. Public page will render unstyled; bypass /_next/* too."
    failures=$((failures + 1))
  fi
fi

echo
echo "PROTECTED — must be stopped by Cloudflare, before the origin"
for p in "${PROTECTED_PATHS[@]}"; do
  probe "$p"
  if [[ "$LOCATION" == *cloudflareaccess.com* ]]; then
    note "ok       $p -> $CODE to Access login"
  elif [[ "$CODE" == "200" ]]; then
    note "FAIL     $p -> 200 WITHOUT A SESSION. This path is open to the internet."
    failures=$((failures + 1))
  else
    note "FAIL     $p -> $CODE and no Access redirect. The origin answered, so Access is not"
    note "         protecting this path. For /api/v1/* a 401 here means only the app refused —"
    note "         the request still reached it. Narrow the bypass."
    failures=$((failures + 1))
  fi
done

echo
if (( failures )); then
  echo "FAILED: $failures problem(s). Do not leave the bypass in this state."
  exit 1
fi
echo "PASSED: marketing pages public, every data-bearing path stopped at the edge."
