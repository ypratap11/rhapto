/** The homepage's one proof, rendered inside the hero: a catch in tune mode, on a sentence from the
 * visitor's own kind of document. Three rows: the resume line, the AI draft that Rhapto stops, and the
 * line Rhapto gives instead. Tune mode is the only path the coach offers, so the rule shown is one tune
 * mode always runs (`no-new-numbers`); the blocks-only rules (`provenance`, `no-unverified-metrics`)
 * are deliberately absent (`engine/guardrails/tune.py` BLOCKS_ONLY).
 *
 * The page shows plain words only. Both engine-checked sentences are pinned in
 * `apps/api/tests/unit/test_guardrails_tune.py`: AI_DRAFT must FAIL (`test_homepage_proof_matches_the_engine_wording`)
 * and RHAPTO_GIVES must PASS (`test_homepage_tailored_line_passes_the_engine`); keep them byte for byte.
 * Every person and employer is fictional. */
import { Check, X } from "lucide-react";
import type { ReactNode } from "react";

export const YOUR_RESUME = "Led the Snowflake migration for 12 teams, cutting warehouse cost 30%.";
/** Must equal `after` in the API test that expects the engine to REJECT it (45 is not in the document). */
export const AI_DRAFT = "Moved 45 teams onto Snowflake and cut data-platform cost 30%.";
/** Must equal `after` in the API test that expects the engine to ACCEPT it. */
export const RHAPTO_GIVES = "Moved 12 teams onto Snowflake and cut data-platform cost 30%.";

/** Split `sentence` around `phrase` so the phrase can be wrapped in a `<mark>`; text order is unchanged. */
function marked(sentence: string, phrase: string, className: string): ReactNode {
  const at = sentence.indexOf(phrase);
  return (
    <>
      {sentence.slice(0, at)}
      <mark className={className}>{phrase}</mark>
      {sentence.slice(at + phrase.length)}
    </>
  );
}

const MARK = "rounded px-0.5 text-foreground";
const ROW = "grid min-w-0 items-center gap-x-3 gap-y-1 border-t border-border px-4 py-3 first:border-t-0 sm:grid-cols-[7.5rem_minmax(0,1fr)_auto] sm:px-5";
const LABEL = "text-xs uppercase tracking-wide text-muted-foreground";
const SENTENCE = "min-w-0 break-words text-[15px]";
const TAG = "inline-flex items-center gap-1 text-[13px] font-semibold";

export function TuneProof() {
  return (
    <div className="mx-auto w-full max-w-3xl overflow-hidden rounded-card border border-border bg-surface text-left shadow-card">
      <p className="sr-only">One sentence from a resume, the AI draft Rhapto stops, and the line Rhapto gives instead.</p>
      <div data-proof-row="resume" className={ROW}>
        <p className={LABEL}>Your resume</p>
        <p data-proof-sentence className={SENTENCE}>
          {marked(YOUR_RESUME, "12 teams", `${MARK} bg-surface-muted`)}
        </p>
      </div>
      <div data-proof-row="draft" className="border-t border-border bg-destructive/[0.06]">
        <div className={`${ROW} border-t-0`}>
          <p className={LABEL}>AI draft</p>
          <p data-proof-sentence className={SENTENCE}>
            {marked(AI_DRAFT, "45 teams", `${MARK} bg-destructive/20`)}
          </p>
          <p className={`${TAG} text-destructive`}>
            <X className="size-3.5 shrink-0" aria-hidden="true" />
            <span>Stopped</span>
          </p>
        </div>
        <p className="px-4 pb-3 text-[13px] text-muted-foreground sm:pl-[9.25rem] sm:pr-5">45 is not in your resume.</p>
      </div>
      <div data-proof-row="gives" className={ROW}>
        <p className={LABEL}>Rhapto gives</p>
        <p data-proof-sentence className={SENTENCE}>
          {marked(RHAPTO_GIVES, "12 teams", `${MARK} bg-fit-high-bg`)}
        </p>
        <p className={`${TAG} text-fit-high`}>
          <Check className="size-3.5 shrink-0" aria-hidden="true" />
          <span>Tailored, true</span>
        </p>
      </div>
    </div>
  );
}
