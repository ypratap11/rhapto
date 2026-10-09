# Homepage coach tour and "same identity, more energy" refresh — design

Status: draft for architect review · Date: 2026-10-09 · Branch: `spec/tour-refresh` (from `main` 73b44d7)

## 1. Why

Two owner observations after the coach shipped (2026-10-09):

1. "Why will a user do it — he wants to tour the product even before he signs up." Today the homepage
   asks for sign-in (Cloudflare Access on `/start`) before a visitor has seen anything of the product.
2. "The whole stack looks dull" compared with jobquest.ai. A scan of 8 competitor homepages
   (`.superpowers/brainstorm/competitor-scan.md`) found a product mockup in the hero on 8/8, one
   saturated accent on 7/8, social proof on 7/8, a tabbed product switcher on 5/8 and gradient or
   motion on 5/8. Rhapto's homepage has none of these.

Owner decisions (2026-10-09, visual companion screen `hero-energy.html`):
- Direction **B, "same identity, more energy"**: keep warm off-white, the brick-red family, Fraunces
  headings and Inter; add a brighter accent, pill buttons, soft depth, colour accents and the product
  in the hero. (The 2026-09-14 indigo/Geist restyle stays rejected.)
- Scope **whole app**, but **working screens stay calm**: decoration only on front pages.
- The tour is **coded mini-screens**, not screenshots.

Success: a signed-out visitor on `/` can step through the four coach screens with fictional data,
without signing in, and the homepage carries the competitor patterns we can claim honestly. No
change to any API, data or sign-in path.

## 2. Homepage (`/`, `components/landing/Landing.tsx`)

Order top to bottom: hero (with tour window) → three steps → TuneProof → "How it works in detail".

### 2.1 Hero
- Background: a radial warm glow (peach → off-white) with two decorative soft shapes (orange, teal),
  `aria-hidden`, `pointer-events-none`. Implemented as a `glow` tone of `HeroBand` (§4), not inline
  per page.
- Pill badge above the headline: "Every number checked against your resume" with a small teal dot.
- Headline text unchanged ("A resume you can defend in any interview."); the word "defend" gets a
  highlighter underline (a background gradient on a `<span>`, not `<mark>` — it is decoration, not
  a search hit). Weight goes from 500 to 600.
- Subline: "Upload your resume, pick a job, and get your own document rewritten for it."
  (No timing promise — the measured median is 105 s on the largest account, not a guarantee.)
- Primary CTA unchanged in target and label logic (`/start` "Tailor my resume" when
  `SAME_ORIGIN_DEPLOYMENT`, else `/settings` "Get started"), gains a trailing "→" and the pill style.
- Secondary link becomes "See how it works ↓", an in-page anchor to the tour window (`#tour`).
  "Request beta access" moves under the button row as a plain text link (still rendered only when
  `SAME_ORIGIN_DEPLOYMENT`, same `accessRequestLink()`).
- Facts strip directly under the buttons, in place of social proof we cannot honestly claim:
  "Open source · You always submit · Every number checked". Each item is a true, permanent property
  of the product; no counts, ratings or logos. No "only"/"first" wording anywhere.
- The free-limit line (`freeLimitLine`) stays, under the facts strip.

### 2.2 Tour window (new `components/landing/CoachTour.tsx`, data in `coachTourData.ts`)
- A framed "app window" (rounded top corners, faint dot bar, soft shadow) sitting at the bottom of
  the hero band, `id="tour"`, with a visible heading for screen readers: "See the coach, step by step".
- Four tabs, WAI-ARIA tabs pattern (`role="tablist"`, `tab`, `tabpanel`, roving `tabIndex`,
  Left/Right/Home/End keys, manual activation is not needed — arrow keys select):
  `1 Upload` · `2 Role` · `3 Top matches` · `4 Your resume`. Opens on tab 1. No autoplay, no timer,
  no scroll-jacking.
- Each panel is a static mini-screen drawn with the app's own tokens, showing the fictional
  Maya Chen (same fictional person as the `/about` tour):
  1. **Upload** — a file chip "maya-chen-resume.docx", status "Read 3 roles, 14 lines".
  2. **Role** — "We think you are aiming for: Technical Program Manager" with a selected chip and two
     unselected alternatives.
  3. **Top matches** — three job rows (title, company, a fit label "Strong match"/"Good match"
     using the real `matchLabel` wording, and a "Tailor this one" pill). Hiring companies are
     fictional (Contoso Robotics, Fabrikam Health, Tailspin Air); no real employer names. Maya's own
     past employers in panel 4 reuse the `/about` tour's fictional set (Northwind Labs, Acme
     Analytics, Globex).
  4. **Your resume** — a document excerpt with one rewritten bullet highlighted as changed and one
     number with a small "checked against your resume" tick.
- Everything inside the panels is display-only: no `<a>`, `<button>`, `<input>` or form inside a
  `tabpanel`; "buttons" are styled `<span>`s with `aria-hidden` where they would otherwise be read as
  controls. The only interactive elements in the window are the four tabs.
- Under the window, always visible: "Example with a fictional person, Maya Chen." and a link
  "Try it with your resume →" to the same target as the primary CTA.
- Data lives in `coachTourData.ts` as plain typed objects (no HTML strings, nothing injected).
- Server-rendered markup must contain all four panels' text (inactive panels `hidden`), so the page
  works and is indexable without JavaScript; the tab switching needs a small client component.
  `Landing.tsx` stays a server component and renders `<CoachTour />`.
- Phone width (≥ 320 px): tabs wrap or scroll horizontally inside the tablist only; no page-level
  horizontal scroll; panels stack their contents.

### 2.3 Three steps
Same three steps and copy. The icon tile becomes a numbered circle in three accent colours
(red `--accent-1`, amber `--accent-2`, teal `--accent-3`, §3) with white numerals; cards use the new
card radius and shadow. Numerals must meet 4.5:1 against their circle, or the circle is
decorative and the number is also in text (as today: "1. ").

## 3. Shared style (globals.css tokens, `components/ui/*`)

All colour pairs used for text must be ≥ 4.5:1 (enforced by the test in §6). Values below are
checked; the implementer may adjust within the same hue only if the test fails.

| Token | Light today → new | Dark today → new | Notes |
|---|---|---|---|
| `--primary`, `--ring`, `--sidebar-primary`, `--chart-1` | `#b4432e` → `#c8401f` | `#e0715a` → `#ec7a5f` | white on `#c8401f` 4.99:1; `#ec7a5f` on `#191614` 6.44:1 |
| `--primary-hover` | `#9a3826` → `#a83417` | `#e98a76` → `#f2937c` | white on `#a83417` 6.63:1 |
| `--link-on-band` (new) | `#9c3a24` | `#f2937c` | text links on the glow/peach band; `--primary` on peach is 4.16:1 and fails |
| `--fit-high` / `--fit-high-bg` | `#2b7349`/`#dff0e5` → `#1d7368`/`#e3f4f1` | → `#6fd1c1`/`#1d3330` | teal "Strong match"; 4.99:1 / 7.37:1 |
| `--accent-1/2/3` (new, decorative) | `#d9482b`, `#e9a23b`, `#2a9d8f` | same | backgrounds/shapes only, never text colour |
| `--glow-from/--glow-mid/--glow-to` (new) | `#ffd7bf`, `#fbe7d8`, `--background` | `#3a2a22`, `#2b2622`, `--background` | hero glow |
| `--radius-card` | `10px` → `12px` | same | |
| `--shadow-card` | neutral → warm tint (`rgb(156 58 36 / …)`) at the same strengths | unchanged | |

`#d9482b` (mockup B's red) is 4.28:1 with white text, so it is decorative only (`--accent-1`).

Components:
- `Button`: `default` and `outline` variants at sizes `default` and `lg` become pill-shaped
  (`rounded-full`); `lg` gets slightly more horizontal padding. `default` hover uses
  `--primary-hover` (today `bg-primary/80`, which lightens toward the background). Icon sizes become
  circles. Button groups keep their joined shape. The primary CTA on front pages gets a soft accent
  shadow; buttons elsewhere get none.
- `Badge`/`StatusBadge`/fit chips: pill radius; fit-high uses the new teal tokens. No wording change.
- Cards (`rounded-card shadow-card`) pick up the new radius and shadow everywhere automatically.

## 4. Where the energy goes (and where it does not)

- `HeroBand` gains `tone="glow"`: radial gradient from the glow tokens plus the two soft shapes
  (replacing `StitchMotif` for that tone only). Used on: `/` (homepage), `/about` hero, `/start`
  (above the coach frame, short height).
- `EmptyState`: the icon sits in a soft tinted circle (`--glow-mid`) instead of a bare grey icon.
- Every other page (dashboard, jobs, my resumes, package/review, pipeline, profile, settings,
  feedback) changes only through the shared tokens and components in §3. Their `HeroBand` tones
  (peach/mint/sand) stay as they are.
- No new animation beyond the existing hover lift. Decoration respects
  `prefers-reduced-motion` trivially (it is static).

## 5. Out of scope

- The 12-step screenshot tour on `/about` (`ProductTour.tsx`, `public/tour/*.webp`, captured
  2026-09-29) shows the older profile/blocks flow, not the coach. Left unchanged here; follow-up:
  restyle, replace with `CoachTour`, or remove.
- Any API, database, auth, Cloudflare Access or env change. Social proof of any kind. New fonts.
  Dark-mode redesign beyond the token values above.

## 6. Testing

- `CoachTour.test.tsx` (vitest + Testing Library):
  - renders four tabs, tab 1 selected, panel 1 visible, panels 2–4 `hidden` but present in the DOM;
  - click and ArrowRight/ArrowLeft/Home/End move selection and `aria-selected`, wrapping at ends;
  - the fictional-data line is present regardless of the selected tab;
  - no `a`, `button`, `input`, `select`, `textarea` inside any `tabpanel` (prove the check fails by
    asserting it against a fixture that contains a link);
  - the "Try it with your resume" link matches the primary CTA target in both deployment modes.
- `Landing.test.tsx` updated: badge, facts strip, "See how it works" anchor to `#tour`, CTA targets
  unchanged in both modes, free-limit line present; no "only"/"first" in rendered text.
- `tokens-contrast.test.ts` (new): parses `globals.css` `:root` and `.dark` blocks and asserts each
  listed text pair ≥ 4.5:1 — at least `primary-foreground/primary`, `foreground/background`,
  `muted-foreground/background`, `fit-high/fit-high-bg`, `fit-mid/fit-mid-bg`,
  `link-on-band/glow-mid`, `link-on-band/band-peach`, `primary/background` — in both themes. Must be
  shown to fail by temporarily setting `--primary` to `#d9482b`.
- Existing tests touching `HeroBand`, `Button`, `EmptyState`, fit labels updated for class changes
  only; no behaviour change expected.
- Visual check before deploy: screenshots of `/`, `/about`, `/start`, dashboard, jobs, a package
  page, in light and dark, at 1440 px and 375 px, shown to the owner for approval. No page-level
  horizontal scroll at 375 px.
- CI as usual (pull request to `main`); no local Docker.

## 7. Risks

- Pill buttons and the warmer shadow touch every page: a layout regression is the main risk; the
  screenshot set in §6 covers the high-traffic pages.
- The tour is a drawing of the coach and can drift from it. Mitigation: the mini-screens use real
  wording helpers where they exist (`matchLabel`), and the fictional-data line sets expectations.
  Any coach copy change should update `coachTourData.ts` (note in the coach components' header).
