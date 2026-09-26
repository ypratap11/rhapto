# Model-optional tailoring — functional spec

**Role 1 of the delivery pipeline (functional architect).** The gate on this document is the owner
confirming it solves the right problem. No architecture, no plan, no code until then.

**Date:** 2026-09-26 · **Status:** awaiting owner confirmation

## The outcome

A person with **no API key and no money** can produce a tailored résumé with Rhapto.

Today they cannot. Every tailoring run needs an LLM provider key, which means the people this project
was built for — someone who has just lost their income — must buy something before Rhapto does anything
for them. On the hosted instance that cost currently falls on the owner instead
(`docs/runbook-access-mode.md`), which is a decision that does not scale past family.

## Why this is possible at all

Most of the pipeline already has no model in it. Measured, not assumed:

| Step | Model? | Notes |
|---|---|---|
| `extract` — JD → structured requirements | **yes** | the easier of the two calls |
| `select` — rank blocks against the job | **no** | `FastEmbedProvider` runs ONNX on CPU; local, free, offline |
| `compose` — write the résumé | **yes** | constrained generation, the hard one |
| `validate` — guardrails | **no** | pure code |
| `repair` — fix violations | yes, when needed | |
| `render` — DOCX/PDF | **no** | `python-docx`, ATS template |

The part that decides *which* of someone's experience matters for a job is already free.

## Scope: a tier below the current one, not a replacement

**`select` mode** — a third mode beside the existing `blocks` and `tune` modes.

1. **No `extract` call.** The job's requirements come from what is already structured: a polled job
   already carries `company` and `title` from the ATS API (`jobs.company`, `jobs.title` are real
   columns), and the user's track already carries curated keywords and a fit threshold. Semantic
   ranking uses local embeddings of the raw JD text.
2. **No `compose` call.** The selected blocks are emitted **verbatim** — the user's own sentences,
   grouped under the ATS template's existing headings, ordered by the rules that already exist
   (Experience reverse-chronological, employment never truncated — the defect fixed in `df358bed`).
3. **Guardrails still run, unconditionally.** They should pass trivially: every bullet's
   `source_block_id` is the block it came from, and no metric can be invented because nothing is
   generated. **If a guardrail ever fails in this mode, that is a bug worth an alert** — it means the
   renderer altered something it was supposed to copy.

### The claim this unlocks

> Every sentence in this document is one you wrote.

That is a stronger statement than any LLM mode can make, and it is verifiable rather than asserted. It
is also the honest version of what the market research identified as the only scarce asset here —
being checkable.

## Acceptance criteria

1. A user with **no provider key configured at all** can tailor a résumé for a polled job and get a
   DOCX and PDF. No API call leaves the machine except the ATS polling that already happens.
2. Every bullet in the output is **byte-identical** to the `content` of a block in the user's library.
   A test asserts this by comparing rendered bullets against block text, not by trusting the renderer.
3. A metric prints **only** if its block is `verified: true` — the same rule as every other mode, and
   it must be asserted by a test that fails if the check is removed.
4. The guardrail report is present, `rules_run` lists all five rules, and `passed` is true. A planted
   unverified metric in a selected block must still be caught.
5. The package records `mode: "select"` so the UI can say, truthfully, that nothing was rewritten.
6. An employment entry is **never dropped**. The failure that produced this rule — a top-K truncation
   silently losing the oldest employer — is asserted directly, with more employment blocks than the
   nominal limit.
7. Selection quality is unchanged from `blocks` mode given the same inputs: the same blocks are chosen.
   This mode changes what happens *after* selection, not selection itself.

## Explicit non-goals

- **No cover note.** It cannot be written without a model, and a template-generated one would be worse
  than none. `blocks` mode keeps it.
- **No rephrasing to mirror the JD's vocabulary.** This is the real cost, stated plainly: tailoring here
  means *which* items appear and in what order, not how they are worded. Keyword screens see the user's
  own words, which may or may not match the posting's.
- **Not a default.** `blocks` mode remains the recommended path for anyone who can afford it.
- **No JD interpretation.** Without `extract` there is no must-have/nice-to-have distinction, no
  seniority inference, no synonym handling. Ranking falls back to embeddings plus the track's keywords.
- **No hand-pasted JD support in the first version.** A pasted JD has no structured company or title;
  polled jobs do. Ask the user, or defer.

## The model ladder, so this is not confused with "local models"

The owner asked whether a small local model would do, "as it is only resume". Measured evidence from
2026-09-25, same job / same profile / same commit:

| Model | Guardrails | Violations |
|---|---|---|
| Claude Opus 5 | passed | 0, kept all 5 employment entries |
| Claude Haiku 4.5 | passed | 0, **but silently dropped one role** |
| Llama 3.3 **70B** | **failed** | 8 |
| Qwen 2.5 **72B** | **failed** | **36**, output looked plausible |

`compose` is not prose writing; it is constrained generation under a strict JSON schema with exact
identifier copying. Two 70B models failed it. A 7–8B model is very unlikely to pass, and where a model
only honours `json_object` rather than a strict schema it fails immediately with a malformed-output
error — which is at least loud.

`extract` is a different and much easier task: read a JD, emit keywords and requirements. A small local
model plausibly handles it, and the guardrail report is already a usable eval for finding out. That is
worth **measuring**, not assuming, and it is a separate piece of work from this spec.

Hardware reality: the production droplet has ~940MB free against ~5GB for an 8B at 4-bit, and hosts
three other projects. **Local models are a self-hosting story only** — they cannot serve invited users
on the hosted instance. `ProviderInfo.base_url` plus `OPENAI_COMPATIBLE` already makes Ollama or vLLM a
single registry entry, so that path needs documentation rather than code.

So the ladder, cheapest first: **`select` mode (no model, free, works today's hardware) → local model
via Ollama, self-host only, `extract` plausible and `compose` doubtful → hosted frontier model.**

## Open questions for the owner

1. **Is a verbatim résumé actually useful to a human reader?** It will read less targeted than a
   composed one. Nobody has evidence either way that tailoring improves interview rate — the business
   plan already marks that as an unmeasured assumption. This mode makes the question sharper rather
   than answering it.
2. **Should `select` mode be offered on the hosted instance, or only to self-hosters?** Offering it
   hosted is what removes the unbounded cost on the owner's provider key. Recommended: offer it
   everywhere, and make it the default when no key is configured rather than showing an error.
3. **Pasted JDs**: ask the user for company and title, or restrict the first version to polled jobs?

## What this does not change

Guardrails stay unconditional. Provenance stays mandatory. Nothing gains an auto-submit path. Imported
blocks stay `verified: false`. No date is ever invented.
