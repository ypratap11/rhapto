# Flow and stage actions

Every stage a job, resume, or application passes through has a way forward and a way out — no
stage is a dead end.

| Stage | Forward | Out |
|---|---|---|
| Job (grid, recommendations, job page) | **Tailor** | **Not interested** hides the job (`jobs.hidden_at`); Undo toast for 8 s; "Show hidden" toggle on Jobs |
| Resume | **Review** → **Mark ready** → **Apply** | **Skip** archives the package (`packages.archived_at`) and hides the job; **Regenerate** makes a new version; **Blocked** lists violations with a Fix link |
| Apply | Opens the posting in a new tab and downloads the resume; on return the card asks "Did you apply?" **Yes / Not yet / Skip** | Yes creates or updates the application as Applied with today's date |
| Your applications (Dashboard) | **Screen → Interview → Offer**, each with date and optional note | **Closed** with reason `rejected \| withdrew \| no_response \| filled`; **Follow-up** date puts a reminder on the Dashboard |

## Not interested

Not interested hides a job from the Jobs grid and the Dashboard's recommendations. It isn't a
permanent delete — a toast offers **Undo** for 8 seconds, and after that the "Show hidden" toggle
on the Jobs page brings hidden jobs back into view (and lets you unhide one) at any time.

## Skip

Skip is the way out of a resume you don't want to pursue. It archives the package and hides the
underlying job in one step, with the same 8-second Undo toast as Not interested. You'll find it as
a row action on the Resumes table, and again inside the "Did you apply?" prompt if you decide not
to after all.

## Blocked

When a guardrail rejects part of a generated resume, the package's status becomes **Blocked**
instead of ready for review. The job page and the review page both show a guardrail panel listing
every violation — which rule failed, what it says, and where — each with a link that jumps straight
to the offending bullet, paragraph, or field so you can fix it and regenerate.

## Closed

An application is closed with one of four reasons, so a closed application always
says why:

- **Rejected** — the employer turned you down.
- **Withdrew** — you pulled out of the process.
- **No response** — the employer went quiet.
- **Filled** — the role was filled by someone else, or pulled entirely.

## Follow-up

Any application can carry a follow-up date. A follow-up due today or overdue puts a "Follow up"
badge on its row in the Dashboard's **Your applications** list, and the last chip in the filter row ("N
follow-ups due") filters to those rows, so it doesn't silently sit unnoticed.

![The job page](../user-guide/images/job-light.png)

## Closed postings and reposts

A job a source no longer returns on two consecutive polls is marked `unlisted_at`: it leaves the
recommendations and the Resumes queue, and any application tied to it shows "No longer listed".
When the same role reappears later — a repost — the new posting's `repost_of` links back to the
original. The new job's card and header carry a Reposted chip, and its page offers "Reuse resume
v{n}" so you don't have to tailor from scratch for a role you've already been through.
