# Guided flow and navigation — design

Date: 2026-09-11. Status: approved in chat; plan to follow. Scope: `apps/web` plus one API change (download
filenames). Builds on the stage 3 web app and phase 0.3 discovery (main at d192d9f or later).

## 1. Problem

After tailoring, the review page is reachable only through a small underlined link under a job card's
description, there is no page that lists tailored packages, and nothing tells the user which job to act on
next. The user asked for a linear flow they can follow and for the app to say "apply to this one first".

## 2. The flow

One linear flow, visible everywhere: **Find → Tailor → Review → Apply**.

- A step bar under the header on every page highlights the current step (Jobs = Find, a running tailor =
  Tailor, the review page = Review, Pipeline = Apply) and shows one prompt line: the most useful next action
  (for example "3 packages ready to review" linking to Packages, or "Next: tailor Scale AI, TPM Enterprise
  (fit 72)" linking to that job).
- Navigation items match the steps: **Jobs**, **Packages**, **Pipeline**, **Profile**, and a Settings icon.

## 3. Jobs page (today's Queue)

- **Next up** panel at the top: "Apply to these first". The top five jobs by fit that are not applied and not
  skipped, ranked 1 to 5, each showing company, title, fit badge, track, and one state-aware button:
  **Tailor** (no package), **Tailoring…** (task running, progress inline), **Review** (package exists,
  application not applied), **Mark applied** (package exists and reviewed; sets application status applied).
  A **Skip** link per row hides that job from Next up (stored per browser in localStorage under
  `rhapto.skipped`, a JSON array of job ids; not a server change).
- Tabs above the list: **New** (no package), **Tailored** (has a package), **Low fit** (bucket low). The
  existing track select and sort toggle stay; the Fit / Low fit toggle is replaced by the tabs. Poll now,
  the runs status line, Add job, and search stay.
- Job card: one primary button whose label follows the same state machine as Next up; the underlined
  "Review package" link is removed. The package badge (`v1 · draft`) and the applied badge remain.

## 4. Packages page (new, `/packages`)

Every package, newest first: company, title, version, status (draft / blocked), application status
(applied or not), fit badge, created time, and a **Review** button. Filter chips: All, Needs review (draft,
not applied), Blocked, Applied. Backed by a new API endpoint `GET /api/v1/packages` (list, newest first,
optional `status` and `applied` query params, includes `job_id`, `company`, `title`, `fit`).

## 5. Review page

- Sticky action bar at the top: **Download PDF**, **Download DOCX**, **Download zip**, **Regenerate**,
  **Mark applied** (or an Applied badge), **Open posting**. Downloads are named
  `<First>_<Last>_Resume.pdf`, `<First>_<Last>_Resume.docx`, `<First>_<Last>_Package.zip` from the profile's
  `name` answer (non-letters replaced by `_`; fallback `Resume`), set by the API's `Content-Disposition` and
  used by the web download helper.
- When the package is blocked, the guardrail panel renders above the resume.
- Bottom: **Next tailored job** link to the next package in the Packages "Needs review" order, or "All
  reviewed" when none.
- Mark applied shows a toast with an "Open pipeline" action.

## 6. Out of scope

Rendering into the user's own template (stage 4), any change to scoring or discovery, the Pipeline board.

## 7. Testing

Vitest for: step bar state and prompt, Next up ranking and state buttons and Skip persistence, Jobs tabs,
Packages page filters, the review action bar names and Mark applied flow, the download filename helper. API
tests for `GET /packages` filters and the `Content-Disposition` names. `pnpm test`, `typecheck`, `lint`,
`build`, and the Python checks stay green; codegen regenerated after the API change.
