# Homepage polish — addendum to 2026-10-09 tour/refresh spec

Status: draft for architect read · Date: 2026-10-10 · Branch `feat/homepage-polish` from `main` 7c518eb
Parent spec: `2026-10-09-homepage-tour-and-visual-refresh-design.md` (shipped as 7c518eb). Everything there stands
unless changed here.

## Owner feedback (2026-10-10, after seeing prod)
1. "The homepage is not aligned center, both web and mobile."
2. "I was assuming the coach automated, not user clicking (this is ancient clicking to go next)."
3. "Check jobquest.ai — it is so elegant — make it feel good." Observed elegance: centred, white space, one subline,
   one CTA, big centred product window labelled "Live demo", no decorative shapes.
4. "Remove about page."
5. "When I click on Rhapto it takes me to Cloudflare." Cause: `TopBar.tsx:99` logo → `/start` in hosted mode; the
   signed-in tabs (Tailor a resume, My resumes, Feedback, Advanced) are shown to signed-out visitors and all hit
   Cloudflare Access. Next.js `<Link>` prefetch of those routes also produces CORS console errors on `/`.

## 1. Header (all pages)
- The logo always links to `/`, in both modes.
- On public routes (`/`, plus `/settings` in token mode — use the existing `PUBLIC_ROUTES` notion from
  `TokenGate.tsx`, one definition), the header shows only: logo, theme toggle, and in hosted mode a "Sign in" pill
  (outline) → `/start`; in token mode a "Get started" link → `/settings` (as the hero CTA). No app tabs, no Advanced
  menu, no settings/help icons on `/`.
- Every link to a protected route in the header and on `/` uses `prefetch={false}` (or is a plain `<a>`), so a
  signed-out visit to `/` makes no request to a protected route (no console errors).
- Inside the app (non-public routes) the header is unchanged on desktop except the logo target.
- **Phones (< md), every page** (owner, 2026-10-10: "jobquest.ai — they just have three dash on right top"): the
  header is one row: logo left, a ☰ menu button right (`aria-label="Menu"`, `aria-expanded`). It opens the existing
  `components/ui/sheet.tsx` from the right, holding that page's header items as a vertical list (public: Sign in /
  Get started, Request beta access in hosted mode, theme toggle; in-app: the tabs, the Advanced pages, settings,
  help, theme toggle). Closes on Escape, on outside click and on navigation. No wrapped two-row header on phones.

## 2. Remove `/about`
- Delete `app/about/`, `components/landing/{About,ProductTour,tourSteps,JourneyWalkthrough,CaughtDemo}` and their
  tests, and `public/tour/*` — but only after confirming by grep that nothing else imports them (TuneProof stays).
- `next.config.ts` `redirects()`: `/about` → `/` permanent (308); keep the `#how` anchor irrelevant.
- Remove every link to `/about` (TopBar "About", Landing "How it works in detail", `lib/feedback.ts` area mapping,
  `HeroBand`/`TokenGate` comments or route lists, `edge-visibility.json` entry — keep the JSON valid and its test
  green). The `HeroBand` `glow` tone stays (used by `/`).
- Anything on `/about` that is a product fact the homepage lacks (pricing = free-limit line, already on `/`) is not
  re-added; nothing else is moved.

## 3. Centred, calmer hero
- Hero content centred horizontally (`text-center`, `mx-auto`, centred button row) at all widths, with one
  consistent content width shared by hero, tour and the sections below (no left-offset; fix the HeroBand inner
  container vs `main` padding mismatch that offsets hero text from the steps).
- Content, top to bottom: headline (unchanged, "defend" highlighted), subline (unchanged), primary CTA pill
  (unchanged target/label), hosted-only "No invite yet? Request beta access" small line, one quiet facts line
  "Open source · You always submit · Every number checked", free-limit line (small). The pill badge and the old
  facts strip are removed ("Every number checked" moves into the facts line). "See how it works ↓" is removed (the
  tour is directly below).
- Background: decorative shapes removed. A faint warm wash at the top fading to `--background` (reuse glow tokens;
  all text pairs stay ≥ 4.5:1 — the contrast suite must stay green).

## 4. Self-playing tour
- The tour window is centred and wide (`max-w-5xl`), with a small "Live demo" chip in the window bar.
- Autoplay: advances 1→2→3→4→1 every 4 s. The active tab shows a thin progress bar filling over the 4 s.
- Pauses while the pointer is over the window or focus is inside it, and when the window is not in the viewport
  (IntersectionObserver). Resumes when those end. A user click/arrow key on a tab selects it and stops autoplay for
  the rest of the visit (the user is driving).
- A visible pause/play button in the window bar (WCAG 2.2.2), labelled "Pause demo"/"Play demo" for screen readers.
- `prefers-reduced-motion: reduce` → no autoplay, no in-panel animation; tabs work as today; the play button can
  still start it.
- In-panel motion (CSS only, ≤ 400 ms, transform/opacity): panel fades/slides in; panel 3's three job rows appear
  staggered; panel 4's changed line gets its highlight after a short delay. No layout shift: the window keeps a fixed
  min-height across panels.
- Everything from the parent spec §2.2 stays: shared coach copy, inert panels, fictional-data line, CTA pairing,
  `keepMounted` panels server-rendered. Autoplay state must not render differently on server vs client
  (hydration-safe: server renders tab 1, autoplay starts after mount).
- Screen readers: autoplay does not move focus and does not announce each change (no live region on the panel).

## 5. Rest of the page
- The steps section gets a centred `h2` "Three steps to a resume you can defend" (visible), cards centred in the
  same content width; the TuneProof card is centred with the same width.

## 5b. UI basics found in self-audit (not raised by the owner; fix in this batch)
- Step cards: remove the duplicate numbering — keep the coloured numeral circle, drop the "1. " text prefix
  (the circle numeral stops being `aria-hidden`, so the number is still read).
- Tour tabs on phones: one row, never wrapped — horizontally scrollable tablist with no visible scrollbar and the
  active tab scrolled into view; reverses the parent spec's "wrap" decision.
- TuneProof card on `/`: replace developer wording with plain words. The rule/ID line ("Stopped by no-new-numbers
  at edits[0]" and "number(s) not found in the document: 45") becomes "Rhapto stopped this draft: 45 is not in
  your resume." Rule IDs stay in the app, not on the homepage.
- Footer on `/` (and in-app, same component): one slim row — "Open source" (GitHub repo link), "Request beta
  access" (hosted only, `accessRequestLink()`), "Feedback" (only inside the app, since it is protected),
  "© 2026 Rhapto". Centred on phones.
- One vertical rhythm on `/`: the same section spacing token between hero, steps, proof and footer.
- Tap targets ≥ 44×44 px on phones for header icons, the ☰ button, the tour pause button and tabs.

## 5c. Feel good, and bring people in (owner: "make it feel good - users need to be on the platform")
- Closing call-to-action section before the footer, centred on a soft warm band: heading "Try it on your own
  resume", one line "Upload a Word file, pick a job, and read the result before you send anything.", the primary CTA
  pill (same target/label as the hero), and in hosted mode "No invite yet? Request beta access". Visitors who
  scroll to the end are never left without a next step.
- Gentle polish, all CSS, all off under `prefers-reduced-motion`: sections fade up 8 px once as they enter the
  viewport (≤ 400 ms, no layout shift, content visible without JS); primary CTA lifts 1 px with a slightly deeper
  shadow on hover; the "Request beta access" links get the same underline-offset hover as the rest of the app.
- No new claims: no user counts, ratings, logos, testimonials or timing promises; no "only"/"first".

## 6. Testing (additions)
- **UI-basics checklist** in QA and final review (owner rule 2026-10-10): centred to one content width; phone header
  one row with ☰; visitors see only visitor links; logo → `/`; tap targets ≥ 44 px; no wrapped controls; no
  developer jargon on `/`; consistent section spacing; footer present; demo autoplays with pause and reduced-motion.

- Header: on `/` in hosted mode, the header contains exactly logo (→ `/`), theme toggle, "Sign in" (→ `/start`);
  no other links; logo → `/` in token mode and inside the app.
- Every `<a>` rendered on `/` whose href is a protected route has prefetch disabled (assert on the rendered markup or
  the Link prop); `/about` redirect present in `next.config.ts` (unit test over the config).
- Tour autoplay with fake timers: advances after 4 s, wraps 4→1; pauses on hover, focus-within, and when not
  intersecting (mock IntersectionObserver); a tab click stops autoplay; pause button toggles and its label flips;
  reduced-motion (mock matchMedia) → no advance.
- Existing claim/contrast/copy-drift tests stay green.
- **QA (mandatory, owner rule 2026-10-10):** build in **hosted mode** and in token mode; as a signed-out visitor on
  `/`, click every link and button (header, hero, tour, sections, footer) and record where each lands; `/about`
  redirects to `/`; zero console errors on `/`; centred layout verified by measuring (hero text box centre within 2 px
  of viewport centre at 1440, 768, 375); autoplay observed advancing in a real browser; reduced-motion emulated.
- Screenshots for the owner before deploy: `/` at 1440 and 375, light and dark, plus a short GIF or 3 frames of the
  tour advancing.

## 7. Out of scope
Signed-in app screens, the coach itself, API/auth/Cloudflare configuration (the `/about` Access rule, if any, is
harmless once the route redirects).
