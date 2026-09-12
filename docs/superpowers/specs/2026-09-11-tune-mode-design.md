# Tune-my-resume mode — design

Date: 2026-09-11. Status: approved in chat; plan to follow. Builds on main after the guided flow (6cb7ad7).

## 1. Goal

Tailor the user's own resume document, changing only what a posting needs, instead of rebuilding a resume from
blocks. The user uploads one DOCX once; every package in tune mode is that document with a small set of
paragraph edits, rendered back in the original format, with the guardrails still enforced.

## 2. Non-goals

Multiple documents per user; non-DOCX uploads; reordering or adding sections; changing titles, companies, or
dates; the block-based mode is unchanged and remains available.

## 3. The resume document

- `POST /api/v1/profile/resume-document` (multipart, one `.docx`, 5 MB cap) stores the file under the packages
  data volume (`<packages_dir>/resume-document/<user_id>/source.docx`, gitignored) and parses it.
- Parsing (`engine/document.py`, python-docx, pure): every non-empty body paragraph becomes
  `DocParagraph(id="p<index>", text, role)` where `role` is one of `name`, `contact`, `heading`, `summary`,
  `competency`, `entry_title`, `entry_org`, `bullet`, `skill`, `credential`, `other`, classified by simple rules:
  heading = short, all-caps, bold; bullet = List Paragraph style or numbering; entry_title = bold with a tab and
  a year pattern; entry_org = the paragraph after an entry_title; competency/skill = `Label:  text` under a
  CORE COMPETENCIES / SKILLS heading; summary = the first paragraph after a SUMMARY heading; credential = under
  EDUCATION; name/contact = first two paragraphs. Section membership is tracked by the nearest heading above.
- The parse is stored as `parsed_json` (`ResumeDocument`: `paragraphs: list[DocParagraph]`, `sections:
  list[{heading, paragraph_ids}]`) on a new `resume_documents` table (one row per user: `user_id`, `filename`,
  `path`, `parsed_json`, `uploaded_at`); `GET /api/v1/profile/resume-document` returns the parse (no file
  bytes); `DELETE` removes it.
- Numbers in the document are the verified set for tune mode: `document_numbers = every metric token found in
  any paragraph` (same tokenizer as the metrics guardrail).

## 4. Tune tailoring

`TailorRequest` gains `mode: "blocks" | "tune"` (default: `tune` when a document exists, else `blocks`; the API
resolves the default). Pipeline in tune mode: extract (call 1, unchanged) → `tune` (call 2) → validate →
(repair, call 3) → render.

`tune` prompt (cached system block: the document paragraphs as `<p id="p12" role="bullet">…</p>` lines plus the
rules; user message: the JD extract). Output schema `TuneOutput`:

```
edits: list[Edit]   # Edit = {paragraph_id: str, text: str, reason: str}
cover_note: str
change_log: str
answers: list[AnswerItem]
```

Rules given to the model: edit only paragraphs whose role is `summary`, `competency`, `skill`, or `bullet`;
at most 6 bullet edits; never edit `name`, `contact`, `heading`, `entry_title`, `entry_org`, `credential`;
keep each edit's meaning and facts, only rephrase and re-emphasise; never introduce a number that does not
already appear in the document; never name an employer, product, or tool not already in the document.

Guardrails in tune mode (new module `guardrails/tune.py`, run by the same registry):
- `tune-scope`: every `paragraph_id` exists and has an editable role (else violation, always on).
- `no-new-numbers`: metric tokens in an edit must be a subset of `document_numbers` (reuses the metrics
  tokenizer; always on).
- `no-invented-entities` reused with the document text as the allowed entity source instead of blocks.
- `date-consistency`: edits must not contain year ranges that differ from the source paragraph's years.
- Provenance in tune mode is the paragraph id; the package's `resume` field stores the edited document as a
  `ResumeDocument` (edited texts applied) and `edits_json` keeps the diff.

Repair (call 3) receives the violations and returns a corrected `TuneOutput`, as today.

## 5. Rendering

`engine/render/tune_docx.py`: open the source DOCX, for each edit replace the paragraph's text keeping the
first run's formatting (drop other runs), save as `resume.docx`; the worker converts to PDF as today. Blocked
packages render nothing new (the guardrail report explains).

## 6. Data and API

- `packages` gains `mode` (`blocks` | `tune`, default `blocks`) and `edits_json` (nullable). `PackageOut` gains
  `mode` and `edits: list[{paragraph_id, before, after, reason}]`.
- `POST /jobs/{id}/tailor` body gains optional `mode`; `TaskOut` unchanged.
- Regenerate and the bullet-edit PATCH work in tune mode by editing paragraph texts (PATCH body carries `edits`
  instead of a resume when `mode == "tune"`); each saved version re-runs the guardrails.

## 7. Web

- Profile → new **Resume document** tab: upload (drag or choose), "Parsed as" preview listing sections and
  paragraphs with their roles, replace and delete buttons, and a note that tune mode is on once a document
  exists.
- Tailor button: a mode toggle (Tune my resume / Build from blocks), defaulting per the API rule.
- Review page in tune mode: instead of the block-provenance resume pane, a **Changes** pane listing each edit as
  before/after (paragraph role and section shown), an inline editor per edit (save creates a new version),
  and the full document text below with edited paragraphs highlighted. Guardrail panel, downloads (named),
  Mark applied, next-job link unchanged.
- Packages page and Next up show a small "tune" or "blocks" chip.

## 8. Testing

Unit: parser roles on a fixture DOCX built in the test (fictional, `Maya Chen`), `document_numbers`, the four
tune guardrails with adversarial cases (new number, invented employer, changed year, edit to a heading),
the DOCX writer (formatting of the first run preserved, other paragraphs byte-identical text). Pipeline: tune
happy path (2 calls), repair path (3 calls), blocked path, with FakeLLM scripted `TuneOutput`s. API: upload,
get, delete, tailor with `mode=tune`, PATCH edits, download names. Web: upload tab, mode toggle default,
Changes pane render and edit-save. Golden: two tune cases.

## 9. Constraints carried over

Max 3 LLM calls per run; prompt-cached static blocks; nothing submits; no personal data in the repo (the
uploaded document is user data on the volume, never in git); TypeScript strict; import-linter contracts.
