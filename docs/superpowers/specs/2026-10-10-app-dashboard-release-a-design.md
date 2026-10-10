# Signed-in app, Release A: one home, two tabs — design

Status: draft for architect review · Date: 2026-10-10 · Branch `feat/app-dashboard` from `main` 34855d6
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
- Phones (< md): one row — logo, a compact **+** button (`aria-label="Tailor a resume"`), ☰ opening the existing sheet
  with the same items grouped: Dashboard, My resumes / Your profile, Settings, Help, Send feedback, Theme, Sign out.
- The logo goes to `/dashboard` on every signed-in page; on visitor pages it stays `/`.
- The visitor header's "Sign in" now goes to `/dashboard` (it is behind Cloudflare Access like `/start`; check
  `edge-visibility.json` / `check-access-boundary.sh` treat `/dashboard` as protected — they must).

## 3. Dashboard (`/dashboard`) — the signed-in home
Centred column (same content width and spacing rhythm as the homepage), top to bottom:
1. **Waiting banner** (only when true): "1 resume is waiting for your review. [Review it →]" (count + link to the
   oldest unreviewed tailored resume). Hidden otherwise.
2. **Your applications**
   - Status chips that filter the list below: **Applied** (`applied` + `screen`), **Interviewing** (`interview`),
     **Offer** (`offer`), **Closed** (`closed`; the row shows the reason in words: Rejected / Withdrew / No response /
     Position filled), **All**. Each chip shows its count; zero-count chips are shown muted, not hidden, once the user
     has at least one application.
   - List rows: company · role · status control (the existing `StatusControl`, relabelled to the words above) · date of
     last change · `›` opening the existing application detail sheet (`ApplicationSheet`). Default filter: All, newest
     first, 10 rows then "Show all".
   - `discovered`/`queued` applications are not shown here (they are jobs, not applications).
3. **Recommended for you** — top 5 recommended jobs as one-line rows: title · company · location/salary when present ·
   match shown as the existing label wording ("Strong match"/"Good match"), not a raw score · outline **Tailor** button
   (→ the existing tailor flow for that job) · ✕ hide (the existing hide/dismiss action, if one exists; otherwise
   omit). Below: "See all matching jobs →" (`/jobs`).
- Removed from the Dashboard: the search form, "Poll now", the saved-searches rail, the multi-row setup checklist
  (replaced by at most one dismissible line "1 thing to finish in your profile ›" when the existing checklist has
  incomplete required items). These capabilities still exist on `/jobs` and `/settings`; nothing is deleted from the API.

### 3.1 Brand-new user states (no zero-count boxes)
- **No resume uploaded:** one centred card: "Start with your resume" · "Upload a Word (.docx) file. Rhapto only ever
  uses what's in it." · button **Upload resume** (→ `/start`). Nothing else.
- **Resume, no applications yet:** chips hidden; one line in their place: "Your applications will show here. After you
  tailor a resume and send it, mark it as applied and track replies here." Recommended jobs below.
- **No recommended jobs yet:** "We're finding jobs that fit you. This usually takes a few minutes." + "Paste a job
  instead" (→ `/start` paste step if addressable, else `/start`).

## 4. Pipeline folds into the Dashboard
- `/pipeline` and `/pipeline/board` redirect (308) to `/dashboard`. The board view is retired; list + sheet remain.
- `/jobs` stays as a page (reached from "See all matching jobs"), with no tab.
- The coach's "Skip to the full app" link becomes "Back to your dashboard" (→ `/dashboard`).

## 5. Clear AI-key errors
- API (`apps/api/src/rhapto/worker/tasks.py` and the task error path): when the failing key is the **user's own**
  stored key and the provider returns an auth error (401/403, codes such as `invalid_api_key`, `expired_secret_key`,
  `token_invalidated`) record a stable error code `user_key_rejected`; for quota/billing errors (429 insufficient_quota
  or equivalent) record `user_key_quota`. The stored task error text must never contain the key (existing `redact`).
- Web (`apps/web/src/lib/coach/errors.ts` and wherever the coach / job page shows task failures): map
  `user_key_rejected` → "Your {Provider} key was refused. It may have expired or been revoked. Paste a new key in
  Settings, then try again." with an **Open Settings** button (→ `/settings`); `user_key_quota` → "Your {Provider}
  account is out of credit. Add credit with {Provider} or paste a different key in Settings." Provider names: OpenAI,
  Anthropic, Google Gemini, Groq. Unknown errors keep today's message.
- Settings shows the same warning beside the AI provider section when the latest run failed with either code.

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
- Errors: API unit tests mapping provider auth/quota errors on a user key to the two codes (and NOT on the deployment
  key, which keeps its current path); web tests for both messages and the Settings button; key never in the message.
- Existing tests updated, not deleted, where behaviour moved.
- QA (owner rules): hosted build as a signed-out visitor (Sign in → Cloudflare, no other protected link) AND signed in
  on prod-like data via the saved test-account session — every header/menu item clicked, Dashboard states, 44 px tap
  targets, no wrapped controls, centred column, light/dark, 1440 and 375; UI-basics checklist from the polish addendum.
