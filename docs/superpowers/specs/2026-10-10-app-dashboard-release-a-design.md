# Signed-in app, Release A: one home, two tabs — design

Status: revision 2 — architect APPROVED WITH CONDITIONS (I1–I7 folded in, `.superpowers/sdd/app-ia/architecture-review.md`) · Date: 2026-10-10 · Branch `feat/app-dashboard` from `main` 34855d6
Evidence: UX audit of every signed-in screen on prod, `.superpowers/sdd/app-ia/ux-audit.md` (screenshots
`C:\Pratap\work\rhapto\.playwright-mcp\app-*.png`). Visual bar: the shipped homepage (calm, centred, plain words).

## 1. Why
Owner (2026-10-10): "the whole inside is confusing (after you sign in)" … "It should be easy — Dashboard shows what you
have applied, rejected, moved etc. status, with potential jobs recommended … 2 tabs max" … "make it simple and elegant".
Audit: the signed-in user lands in two products sewn together (the calm coach vs the older dense Dashboard / Jobs /
Pipeline / Profile behind "Advanced"); there is no home (logo → marketing page, "Skip to the full app" → a Dashboard
missing from the nav); the same status lives on three screens; a rejected own AI key shows only "The run didn't finish".

Success: after sign-in a user sees ONE home that answers "where are my applications?" and "what should I apply to
next?", with at most two tabs and one obvious primary action; a rejected AI key tells them exactly what to do.

## 2. Header (signed-in pages; the visitor header from 34855d6 is unchanged)
- Desktop: `Rhapto` (→ `/dashboard`) · tabs **Dashboard** · **My resumes** · primary pill **+ Tailor a resume**
  (→ `/start`) · avatar button (user's initial; `aria-label="Account"`) opening a menu: **Your profile** (`/profile`),
  **Settings** (`/settings`), **Help** (`/settings#help` until Release B), **Send feedback** (opens the existing
  feedback dialog — no `/feedback` tab), **Theme** (light/dark toggle), **Sign out** (the existing Cloudflare Access
  logout URL if one exists in the code; otherwise omit and note it).
- Removed: the "Advanced" menu, the "Feedback" tab, the "Tailor a resume" tab (it is the button now), the standalone
  feedback/settings/help icons.
- **Sign out** (hosted mode only): Cloudflare Access's standard `/cdn-cgi/access/logout`. Token mode has no sign-out
  item (no code-level logout exists).
- Menus (I6): the avatar is a disclosure button (`aria-expanded`, not `role=menu`), Escape closes and returns focus to
  it; Theme item has a visible text label ("Dark mode" / "Light mode"). The feedback dialog's open state lives in
  TopBar and the dialog renders once outside both menus, so choosing "Send feedback" closes the menu and opens the
  dialog.
- Phones (< md): one row — logo, a compact **+** button (`aria-label="Tailor a resume"`), ☰ opening the existing sheet
  with the same items grouped: Dashboard, My resumes / Your profile, Settings, Help, Send feedback, Theme, Sign out.
- The logo goes to `/dashboard` on every signed-in page; on visitor pages it stays `/`.
- The visitor header's "Sign in" now goes to `/dashboard` (it is behind Cloudflare Access like `/start`; check
  `edge-visibility.json` / `check-access-boundary.sh` treat `/dashboard` as protected — they must).

## 3. Dashboard (`/dashboard`) — the signed-in home
Centred column (same content width and spacing rhythm as the homepage), top to bottom:
1. **Waiting banner** (only when true): "1 resume is waiting for your review. [Review it →]" — count is the existing
   `needs_review_count` (latest-version packages in `draft`), link → `/resumes?tab=review`. Hidden when 0.
2. **Your applications**
   - Status chips that filter the list below: **Applied** (`applied` + `screen`), **Interviewing** (`interview`),
     **Offer** (`offer`), **Closed** (`closed`; the row shows the reason in words: Rejected / Withdrew / No response /
     Position filled), **All**. Badge words per status: applied → Applied, screen → Screening (counted under the
     Applied chip), interview → Interviewing, offer → Offer, closed → its reason. Each chip shows its count; zero-count chips are shown muted, not hidden, once the user
     has at least one application.
   - List rows (I1): company · role · a status **badge** in the words above · date of last change · `›`. The whole row
     opens ONE application sheet (I2) containing: the existing `StatusControl` (status, closed reason, follow-up date),
     notes, history, "Open the resume used", and Delete. It replaces both `ApplicationSheet` (board-only) and the
     `ApplicationDetail` page content; the Board, its Column/Card parts and their tests are deleted. Default filter:
     All, newest first, 10 rows then "Show all".
   - `discovered`/`queued` applications are not shown here (they are jobs, not applications).
3. **Recommended for you** — top 5 recommended jobs as one-line rows: title · company · location/salary when present ·
   match shown as the existing label wording ("Strong match"/"Good match"), not a raw score · outline **Tailor** button
   (→ the existing tailor flow for that job) · ✕ hide (existing `useHideJob`). Below: "See all matching jobs →" (`/jobs`).
- Removed from the Dashboard: the search form, "Poll now", the saved-searches rail, the multi-row setup checklist
  (replaced by at most one dismissible line "1 thing to finish in your profile ›" when the existing checklist has
  incomplete required items). The search form and saved searches already exist on `/jobs`/`/settings`; **"Poll now"
  moves to the `/jobs` page header** (I3; `PollNowButton` is used only by `DashboardHero` today). Nothing is deleted
  from the API.

### 3.1 Brand-new user states (no zero-count boxes)
- **No resume uploaded:** one centred card: "Start with your resume" · "Upload a Word (.docx) file. Rhapto only ever
  uses what's in it." · button **Upload resume** (→ `/start`). Nothing else.
- **Resume, no applications yet:** chips hidden; one line in their place: "Your applications will show here. After you
  tailor a resume and send it, mark it as applied and track replies here." Recommended jobs below.
- **No recommended jobs yet:** "We're finding jobs that fit you. New jobs arrive through the day." + "Paste a job
  instead" (→ `/start`). No timing promise (I3: the scheduled poll runs every few hours).

## 4. Pipeline folds into the Dashboard
- `/pipeline` and `/pipeline/board` redirect (308) to `/dashboard`. The board view is retired; list + sheet remain.
- `/jobs` stays as a page (reached from "See all matching jobs"), with no tab.
- The coach's "Skip to the full app" link becomes "Back to your dashboard" (→ `/dashboard`).
- Every other `/pipeline` link and label moves to `/dashboard` with dashboard wording (I7): `DidYouApplyPrompt`,
  `PackageActions`, `JobHeader`, the `ApplicationDetail` breadcrumb, `HelpSection`'s docs link, and the stale
  "not redirected" note in `next.config.ts` and its test.

## 5. Clear AI-key errors (I4, I5)
- No new column, no migration: the task's existing error text carries one of two **fixed sentences**, chosen in the API
  and recognised by the web the same way the existing shared-key message is (`SETTINGS_SENTENCES` in
  `lib/coach/errors.ts`).
- API: `ProviderAuthError` gains `kind: "auth" | "quota"`. Each provider adapter classifies: auth = 401/403 /
  invalid / expired / revoked key; quota = insufficient credit / billing (including Anthropic credit errors, which
  today do not become `ProviderAuthError`). In `worker/tasks.py`, when the run used the **user's own stored key**, the
  provider name comes from `stored_llm_config` (so Groq/OpenRouter keys are named correctly, not "openai"), and the
  stored error becomes exactly:
  - auth: "Your {Provider} key was refused. It may have expired or been revoked. Paste a new key in Settings, then try again."
  - quota: "Your {Provider} account is out of credit. Add credit with {Provider} or paste a different key in Settings."
  Provider display names: OpenAI, Anthropic, Google Gemini, Groq, OpenRouter. The deployment-key path is unchanged.
  The key never appears (existing `redact` still applies).
- Web: both sentences (any provider) are shown verbatim with an **Open Settings** button (→ `/settings`) wherever a
  task failure is shown (coach tailor/result steps, job page). Unknown errors keep today's message.
- Cut from Release A: the Settings "latest run failed" warning (needs an endpoint that does not exist).

## 6. Out of scope (Release B)
My resumes cleanup, the tailored-resume page (tokens/cost/IDs, readable truth check), the job page's single button,
the vocabulary pass across Profile/Settings, a real Help page. No API schema changes beyond the error code; no
migration.

## 7. Testing
- Header: signed-in tabs exactly Dashboard + My resumes; "+ Tailor a resume" → `/start`; avatar menu items and targets;
  logo → `/dashboard` in-app and `/` on visitor pages; phone ☰ grouping; no "Advanced"/"Feedback" tab.
- Dashboard: chip counts and filtering from fixture applications covering every status and closed reason; row status
  change uses the existing mutation; recommended list capped at 5 with the label wording; every brand-new-user state;
  waiting banner only when an unreviewed tailored resume exists.
- Redirects: `/pipeline`, `/pipeline/board` → `/dashboard` (config test); Sign in → `/dashboard`.
- Errors: API unit tests per provider adapter for auth vs quota classification (incl. Anthropic credit errors), and in
  the worker: user key → the two exact sentences with the correct provider name (Groq/OpenRouter not "openai"),
  deployment key → unchanged path; web tests for both sentences and the Settings button; key never in the message.
- Application sheet: status/closed-reason/follow-up/notes/delete work from the Dashboard; Board routes gone.
- Menus: feedback dialog opens from both menus and stays open; Escape returns focus; Sign out only in hosted mode.
- Existing tests updated, not deleted, where behaviour moved.
- QA (owner rules): hosted build as a signed-out visitor (Sign in → Cloudflare, no other protected link) AND signed in
  on prod-like data via the saved test-account session — every header/menu item clicked, Dashboard states, 44 px tap
  targets, no wrapped controls, centred column, light/dark, 1440 and 375; UI-basics checklist from the polish addendum.
