/** The homepage's one proof: a catch in tune mode, on a sentence from the visitor's own kind of
 * document. Tune mode is the only path the coach offers, so the rule shown is one tune mode always
 * runs (`no-new-numbers`, with `tune-scope`; `no-invented-entities` is user-configurable, so it is
 * not the headline claim). The blocks-only rules (`provenance`, `no-unverified-metrics`) are
 * deliberately absent: tune mode skips them (`engine/guardrails/tune.py` BLOCKS_ONLY), and the
 * homepage does not show them.
 *
 * Inside a run the rejected draft is discarded after a repair; the visitor sees the rule only when the
 * package ends up blocked. So the copy says what happens inside a run and never "you see every catch".
 *
 * The page shows plain words only; the rule id, path and engine message stay in the app. The catch itself
 * (45 is not in the document) is pinned against the engine by
 * `apps/api/tests/unit/test_guardrails_tune.py::test_homepage_proof_matches_the_engine_wording`.
 * Every person and employer is fictional. */
import { ShieldAlert } from "lucide-react";

const BEFORE = "Led the Snowflake migration for 12 teams, cutting warehouse cost 30%.";
const INVENTED = "45";

export function TuneProof() {
  return (
    <div className="mx-auto w-full max-w-5xl rounded-card border border-border bg-surface p-5 shadow-card">
      <p className="text-sm font-medium text-muted-foreground">A real kind of catch, on a resume like yours</p>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <div>
          <p className="text-xs uppercase tracking-wide text-muted-foreground">Your resume says</p>
          <p className="mt-1 text-sm">{BEFORE}</p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-wide text-muted-foreground">The AI&rsquo;s first draft said</p>
          <p className="mt-1 text-sm">
            Led the Snowflake migration for <mark className="rounded bg-destructive/15 px-0.5 text-foreground">{INVENTED}</mark> teams, cutting warehouse cost 30%.
          </p>
        </div>
      </div>
      <div className="mt-4 flex items-start gap-3 rounded-control border-l-4 border-destructive bg-surface-muted p-3">
        <ShieldAlert className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden />
        <p className="min-w-0 text-sm">{`Rhapto stopped this draft: ${INVENTED} is not in your resume.`}</p>
      </div>
      <p className="mt-3 text-sm text-muted-foreground">
        Inside a run, Rhapto checks the draft against your own document. A number that is not in your
        resume is sent back for one fix; if the fix fails, the draft is blocked and you are told why. Then
        you read it, and you press submit.
      </p>
    </div>
  );
}
