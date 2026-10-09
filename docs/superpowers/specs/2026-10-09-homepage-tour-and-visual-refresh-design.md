# Homepage coach tour and "same identity, more energy" refresh — design

Status: revision 2 (architect review `.superpowers/sdd/tour-refresh/architecture-review.md`, APPROVED WITH
CONDITIONS; all conditions addressed below) · Date: 2026-10-09 · Branch: `spec/tour-refresh` (from `main` 73b44d7)

## 1. Why

Two owner observations after the coach shipped (2026-10-09):

1. "Why will a user do it — he wants to tour the product even before he signs up." `/` and `/about` are
   public (since 2026-09-26), but the coach itself (`/start`) sits behind sign-in, and nothing public shows
   what the coach looks like. The `/about` tour shows the older profile/blocks flow.
2. "The whole stack looks dull" compared with jobquest.ai. A scan of 8 competitor homepages
   (`.superpowers/brainstorm/competitor-scan.md`) found a product mockup in the hero on 8/8, one saturated
   accent on 7/8, social proof on 7/8, a tabbed product switcher on 5/8 and gradient or motion on 5/8.

Owner decisions (2026-10-09, visual companion `hero-energy.html`):
- Direction **B, "same identity, more energy"**: keep warm off-white, the brick-red family, Fraunces
  headings and Inter; add pill buttons, soft depth, colour accents and the product in the hero. (The
  2026-09-14 indigo/Geist restyle stays rejected.)
- Scope **whole app**, but **working screens stay calm**: decoration only on front pages.
- The tour is **coded mini-screens**, not screenshots.

Success: a signed-out visitor on `/` can step through four coach screens with fictional data, without
signing in, seeing the coach's real wording; the homepage carries the competitor patterns we can claim
honestly; every text colour pair passes WCAG AA, enforced in CI. No change to any API, data or sign-in path.

## 2. Homepage (`/`, `components/landing/Landing.tsx`)

Order: hero (with tour window inside the band) → three steps → TuneProof → "How it works in detail".
The page has three `<section>`s: tour, steps, proof (`Landing.test.tsx`'s "exactly 2 sections" becomes 3).
The `Landing.tsx` header comment is updated: the coach tour is on `/`; the older 12-step tour stays on `/about`.

### 2.1 Hero
- Background: `HeroBand tone="glow"` (§4): radial gradient `--glow-from` → `--glow-mid` → `--glow-to`, with
  two soft decorative shapes (`--decor-amber`, `--decor-teal`, low opacity), `aria-hidden`,
  `pointer-events-none`.
- Pill badge above the headline: "Every number checked against your resume" with a small teal dot. (The facts
  strip below does not repeat this; M9.)
- Headline text unchanged ("A resume you can defend in any interview."); "defend" gets a highlighter underline
  (background gradient on a `<span>`, not `<mark>`). Weight 600 here **and** on `/about`'s identical headline.
- Subline: "Upload your resume, pick a job, and get your own document rewritten for it." No timing promise.
- Primary CTA: unchanged targets and labels (`/start` "Tailor my resume" when `SAME_ORIGIN_DEPLOYMENT`, else
  `/settings` "Get started"), plus a trailing "→" and a soft accent shadow (`--shadow-cta`).
- Secondary link: "See how it works ↓" → `#tour`, in **both** modes (replaces token mode's `/about#how`).
- Hosted mode only: "No invite yet? Request beta access" (same `accessRequestLink()`) under the button row.
- Facts strip under the buttons: "Open source · You always submit · Your own document". Permanent true
  properties; no counts, ratings, logos. No "only"/"first" claims anywhere.
- The free-limit line (`freeLimitLine`) stays under the facts strip.
- All hero text links use `--link-on-band`; muted text uses `--muted-foreground` (passes on `--glow-from`, §3).

### 2.2 Tour window (new `components/landing/CoachTour.tsx`, data in `coachTourData.ts`)
- A `<section id="tour" aria-labelledby=…>` with `scroll-mt-20`, at the bottom of the hero band, drawn as a framed
  "app window" (rounded top corners, faint dot bar, `--shadow-card`). Visible `h2`: "See the coach, step by step".
- Built on the existing `components/ui/tabs.tsx` (Base UI Tabs): `TabsList` with `activateOnFocus` and
  `loopFocus`; `TabsPanel` with `keepMounted` so all four panels are server-rendered (inactive ones hidden) and
  each panel is focusable with `aria-labelledby`. Tabs: `1 Upload` · `2 Role` · `3 Top matches` ·
  `4 Your resume`. Opens on tab 1. No autoplay, no timer, no scroll-jacking. The list's shadcn sizing
  (`h-8 w-fit`) is overridden so the tabs **wrap** at 320 px; no page-level horizontal scroll.
- `CoachTour` is a `"use client"` component; `Landing.tsx` stays a server component.
- Panels reproduce the coach's **real** titles, hints, button labels and match labels. These strings move into a
  new shared module `lib/coach/copy.ts` that both the coach step components and `coachTourData.ts` import, so a
  copy change in the coach changes the tour, and a test fails if a panel shows a string the coach does not:
  1. **Upload** — title "Upload your resume", hint "A Word (.docx) file, up to 5 MB.", a file chip
     "maya-chen-resume.docx", and the transcript line the coach shows after upload ("Resume: maya-chen-resume.docx").
     No invented status line.
  2. **Role** — the coach's role question ("Looks like you're aiming for: Data Program Manager. Right?") with its
     two buttons ("Yes, that's right" / "Something else"), via a `roleQuestion(name)` helper the real `RoleStep`
     also uses.
  3. **Top matches** — title "Your top matches for Data Program Manager", three job rows (title, fictional company,
     `matchLabel` chip, "Tailor this one"). Companies: Contoso Robotics, Fabrikam Health, Tailspin Air.
  4. **Your resume** — title "Your tailored resume", "Ready for you to read. Check it before you send it.",
     "Download DOCX" / "Download PDF", and a "What changed" list with two short fictional changes. Maya's past
     employers, if shown, are the `/about` tour's fictional set (Northwind Labs, Acme Analytics, Globex).
  Maya is a "data program manager" on both tours (M8).
- Match-label decision (I3): the coach's own `MatchesStep` label becomes a chip — "Strong match" on
  `--fit-high`/`--fit-high-bg`, "Good match" on `--surface-muted`/`--muted-foreground` — and the tour draws it the
  same way. Wording unchanged.
- Everything inside the panels is inert: no `a`, `button`, `input`, `select`, `textarea` inside a panel; drawn
  buttons are `<span aria-hidden="true">` with the label repeated as plain text where it carries meaning. The
  only interactive elements in the window are the four tabs.
- Under the window, always visible: "Example with a fictional person, Maya Chen." and "Try it with your resume →"
  (same target as the primary CTA), plus, in hosted mode, "No invite yet? Request beta access" beside it (I8).
  Token mode shows neither `/start` nor the request link, as today.

### 2.3 Three steps
Same steps and copy. The icon tile becomes a numbered circle with a visible numeral, each pair ≥ 4.5:1 in both
themes (I1): 1 = white on `--primary`, 2 = `--foreground` (#1c1917) on `--decor-amber` (8.07), 3 = white on
`--fit-high` (5.67 light). In dark mode the circles keep their light-mode fills and numerals (absolute colours,
via dedicated tokens `--step-1/2/3` and `--step-1/2/3-fg`). Cards use the new radius and shadow. "1. " stays in text.

## 3. Shared style (globals.css tokens, `components/ui/*`)

Every pair used for text must be ≥ 4.5:1 in both themes, enforced in CI (§6). The "energy" comes from the glow,
decorative colours, pills, depth and the CTA shadow — **not** from a brighter text red (C1: no shade of this hue
bright enough to read as "more energy" passes as text on the tinted surfaces the working screens use).

| Token | Light today → new | Dark today → new | Notes |
|---|---|---|---|
| `--primary`, `--ring`, `--sidebar-primary`, `--chart-1` | `#b4432e` → `#b63a1c` | `#e0715a` → `#ec7a5f` | slightly more saturated; light passes on peach 4.68, mint 4.83, sand/surface-muted 4.95, primary-10% chip 4.73, white-on 5.82; dark 4.90–5.92 on bands/surface |
| `--primary-hover` | `#9a3826` → `#9c3a24` | `#e98a76` → `#f2937c` | white on `#9c3a24` 6.90 |
| `--link-on-band` (new) | `#9c3a24` | `#f2937c` | text links on any band/glow (fixes today's 4.47 fail on peach in `Landing`/`About`, M1) |
| `--fit-high` / `--fit-high-bg` | `#2b7349`/`#dff0e5` → `#1d7368`/`#e3f4f1` | → `#6fd1c1`/`#1d3330` | teal; 4.99 / 7.37 |
| `--decor-red/-amber/-teal` (new) | `#d9482b`, `#e9a23b`, `#2a9d8f` | same | shapes and fills only, never a text colour (renamed from `--accent-n` to avoid shadcn `--accent`, M3) |
| `--step-1/2/3`, `--step-1/2/3-fg` (new) | see §2.3 | same as light | numerals pass 5.82 / 8.07 / 5.67 |
| `--glow-from/--glow-mid/--glow-to` (new) | `#ffe0cc`, `#fbe7d8`, `var(--background)` | `#3a2a22`, `#2b2622`, `var(--background)` | `--glow-from` lightened from `#ffd7bf` so muted text passes (4.77; I2) |
| `--radius-card` | `10px` → `12px` | same | |
| `--shadow-card`, `--shadow-card-hover` | neutral → warm tint `rgb(156 58 36 / …)` at the same strengths | unchanged | M10 |
| `--shadow-cta` (new) | `0 6px 14px rgb(182 58 28 / 0.28)` | `0 6px 14px rgb(0 0 0 / 0.45)` | front-page primary CTA only |

New colours are wired through `@theme inline` (`--color-link-on-band`, `--color-glow-*`, `--color-decor-*`,
`--color-step-*`) and the shadow utilities follow the existing `@utility shadow-card` pattern (M3, M10).

Success colour (M4): `--fit-high` is also the app's "done/success" colour (ProfileChecklist, TaskProgress,
LlmProviderSection); success turns teal with it, intentionally. `--diff-add`/`--chart-2` stay green `#2b7349`
(diff "added" is a different meaning). `TaskProgress.tsx`'s `text-accent` misuse is fixed to `text-fit-high`.

Components (I5):
- `Button`: base radius becomes `rounded-full` for **every** variant except `link`; the explicit radius on sizes
  `xs`, `sm`, `icon-xs`, `icon-sm` (`rounded-[min(var(--radius-md),…)]`) is removed so all sizes are pills or
  circles; `in-data-[slot=button-group]:rounded-lg` becomes `rounded-full`. `lg` gets `px-4`. `default` hover
  uses `bg-primary-hover` (today's `bg-primary/80` gives white text 3.91 — a fix). No shadow except the front-page
  CTA (`shadow-cta`, applied at the call site).
- `PackageActions` button-group container: `rounded-control` → `rounded-full`.
- `ProductTour.tsx` (`/about`) hand-rolled `rounded-control` buttons switch to `buttonVariants` so `/about` has one
  shape; its `bg-primary/90` hover goes to `bg-primary-hover`. No other change to that tour.
- Any call site layering `rounded-card/control/chip` onto a `Button` is replaced, not layered (`cn` does not merge
  custom theme keys).
- `Badge`: hover `[a]:hover:bg-primary/80` → `bg-primary-hover` (M11).
- `StatusBadge`: deliberate reversal of the 2026-09 "6px chips" decision — `rounded-chip` removed, chips become
  pills like `Badge`; the header comment and `StatusBadge.test.tsx` are updated (M5).

## 4. Where the energy goes (and where it does not)

- `HeroBand` gains `tone="glow"` (gradient + two shapes, replacing `StitchMotif` for that tone only). Used on `/`
  and `/about` only. `/start` is **not** changed (I6): it has no band, and on a phone a band would push the upload
  button down.
- `EmptyState`: the icon sits in a soft tinted circle (`--glow-mid` light / `--surface-muted` dark). This shows on
  working screens (jobs, resumes); accepted as the one small exception (M11).
- Pages with a `HeroBand` keep their existing tones: dashboard, jobs, pipeline, profile, resumes (M2). Settings,
  feedback, package/review and the coach have no band and change only through §3.
- No new animation beyond the existing hover lift.

## 5. Out of scope

- The `/about` 12-step tour's content and screenshots (older blocks flow, captured 2026-09-29). Only its buttons
  change shape (§3). Follow-up: replace with `CoachTour` or remove.
- Any API, database, auth, Cloudflare Access or env change. Social proof of any kind. New fonts. A dark-mode
  redesign beyond the token values above.

## 6. Testing

- **One contrast checker, in CI (I7, C1).** Move the `PAIRS` list and the `globals.css` parser from
  `scripts/check-contrast.mjs` into one module (e.g. `src/lib/contrast/`), consumed by a vitest test so
  `pnpm test` (which CI runs) enforces it; the script stays as a thin CLI over the same module. The parser resolves
  `var(--background)` for `--glow-to` (or excludes it explicitly). Text-on-band links are reclassified from `ui`
  (3:1) to `text` (4.5:1). Pairs, both themes: `primary` as text on `background`, `surface`, `surface-muted`, all
  three bands, `glow-mid`, `glow-from`, and the primary-10% chip composite over `surface` and over `background`;
  `link-on-band` on all bands and glow stops; `muted-foreground` on `background`, bands, `glow-from`, `glow-mid`;
  `primary-foreground` on `primary` and `primary-hover`; `fit-high`/`fit-high-bg`, `fit-high`/`surface`,
  `fit-mid`/`fit-mid-bg`; `muted-foreground`/`surface-muted`; the three `step-n-fg`/`step-n` pairs. Known-bad
  proof: the test is shown to fail with `--primary: #c8401f` (fails only on tinted surfaces, 4.24 on
  `surface-muted`).
- **`CoachTour.test.tsx`**: four tabs, tab 1 selected, all four panels in the DOM; click and
  ArrowRight/ArrowLeft/Home/End move selection, wrapping; fictional-data line always present; no interactive
  element inside any panel (proven to fail on a fixture panel containing a link); "Try it with your resume" matches
  the primary CTA in both modes; request-access link present in hosted mode only.
- **Copy-drift test**: every coach string a panel displays comes from `lib/coach/copy.ts`; the coach step components
  render the same constants (existing coach tests updated to import them).
- **Claim test (I4)** in `Landing.test.tsx`: rendered text has no match for
  `/\b(the\s+)?(only|first)\s+(tool|app|product|copilot|resume\s+(tool|builder)|one)\b/i`; proven to fail on
  "The only resume tool that…" and to pass on the free-limit line ("your first resume import") and TuneProof
  ("first draft").
- **Landing invariants (M6)**: `Landing.test.tsx` updated — 3 sections; `#tour` present on `/`; "See how it
  works" → `#tour` in both modes; CTA targets unchanged in both modes; free-limit line present; request-access link
  hosted-only.
- Existing tests touching `HeroBand`, `Button`, `StatusBadge`, `EmptyState`, `MatchesStep`, fit labels updated for
  class changes only.
- `scripts/check-no-personal-data.py` run on the branch (M8).
- **Visual check before deploy**: screenshots of `/`, `/about`, `/start` (upload screen), dashboard, jobs,
  `/settings` (LLM remove dialog open), a package page with the download group, in light and dark, at 1440 px and
  375 px, shown to the owner. No page-level horizontal scroll at 375 px.
- CI as usual (pull request to `main`); no local Docker.

## 7. Risks

- Pill buttons and the warmer shadow touch every page; the screenshot set in §6 covers the mixed-row pages.
- The tour is a drawing of the coach. The shared copy module makes wording drift fail a test; layout drift is
  still possible and is accepted.
- The red only shifts slightly (`#b4432e` → `#b63a1c`); if the owner finds the result still not lively enough,
  the next lever is more decor colour on front pages, not a brighter text red.
