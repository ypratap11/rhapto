#!/usr/bin/env python3
"""Phase 4 measurement (completeness guardrail): run one JD through `tailor()` once per configured
model and record, per model, which rules the FIRST compose failed, whether repair ran and fixed it,
and the final outcome, call count and token usage, to a JSON ledger.

Manual, not part of CI: needs real provider API keys in the environment/.env. Run from the repo
root with:

    uv run --project apps/api python scripts/measure_completeness.py \\
        --jd path/to/jd.txt --profile ./profile \\
        --provider anthropic:claude-haiku-5 --provider anthropic:claude-sonnet-5

`--profile` takes any profile directory. The owner's real profile may fail the strict schema on
load (see the scratch-copy note in the owner's memory); point it at the scratch copy in that case.
The ledger holds rule names, block ids and counts only -- never title, block or resume text -- so
it is safe to produce from a real profile. A failed target is recorded under "failures" with its
provider, model and exception class name only (messages can embed profile content or LLM output),
and the script then exits nonzero.

Reading the output: `first pass failed: completeness` is a model that dropped a selected block.
`repaired (...)` means the one repair call restored it; `blocked after repair (...)` means it did
not. Both read `TailorResult.pre_repair_report`, not `llm_calls`, so a malformed-output retry is
never mistaken for a repair. `invented_project_titles` lists the ids of project blocks whose entry
title or role text is not made of words from the block it cites (the count is printed), and
`unchecked_project_entries` counts project entries citing an unknown block id, which that check
cannot judge: no
guardrail validates a title, so this is the only place the U-1 risk (models inventing a title for
a project block with no role) shows up. Look the ids up in the profile to inspect them.
That repair-success rate, per model, is the number architecture
condition C6 says decides whether the deterministic entry skeleton (Phase 6) is needed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from rhapto.cli.main import build_providers
from rhapto.config import get_settings
from rhapto.engine.measurement import (
    collect,
    exit_code,
    final_rules,
    first_pass_rules,
    format_failure,
    invented_project_titles,
    ledger_document,
    summarize_result,
    unchecked_project_entries,
)
from rhapto.engine.pipeline import tailor
from rhapto.engine.types import Profile, TailorRequest
from rhapto.profile.loader import load_profile


@dataclass
class MeasurementRow:
    provider: str
    model: str
    verdict: str
    first_pass_rules: list[str]
    repaired: bool
    final_rules: list[str]
    invented_project_titles: list[str]  # block ids, never title text
    unchecked_project_entries: int  # project entries citing an unknown block id: not judged above
    status: str
    llm_calls: int
    input_tokens: int
    output_tokens: int


async def _run_one(profile: Profile, jd_text: str, provider: str, model: str) -> MeasurementRow:
    providers = build_providers(get_settings(), provider, model)
    result = await tailor(
        TailorRequest(jd_text=jd_text), profile, providers.llm, providers.embedder
    )
    package = result.package
    return MeasurementRow(
        provider=provider,
        model=model,
        verdict=summarize_result(result),
        first_pass_rules=first_pass_rules(result),
        repaired=result.repaired,
        final_rules=final_rules(result),
        invented_project_titles=invented_project_titles(result, profile.block_map()),
        unchecked_project_entries=unchecked_project_entries(result, profile.block_map()),
        status=package.status,
        llm_calls=package.llm_calls,
        input_tokens=package.usage.input_tokens,
        output_tokens=package.usage.output_tokens,
    )


def _parse_target(parser: argparse.ArgumentParser, raw: str) -> tuple[str, str]:
    provider, sep, model = raw.partition(":")
    if not sep or not provider or not model:
        parser.error(
            f"--provider expects PROVIDER:MODEL (for example anthropic:claude-haiku-5), got {raw!r}"
        )
    return provider, model


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jd", type=Path, required=True)
    parser.add_argument("--profile", type=Path, default=Path("./profile"))
    parser.add_argument(
        "--provider",
        action="append",
        required=True,
        dest="targets",
        metavar="PROVIDER:MODEL",
        help="repeatable, e.g. --provider anthropic:claude-haiku-5",
    )
    parser.add_argument("--out", type=Path, default=Path("completeness-measurement.json"))
    args = parser.parse_args()

    targets = [_parse_target(parser, raw) for raw in args.targets]
    try:
        jd_text = args.jd.read_text(encoding="utf-8")
    except OSError as exc:
        # One line, no traceback; the class name only, like every other failure this script prints.
        print(f"cannot read --jd {args.jd}: {type(exc).__name__}", file=sys.stderr)
        return 1
    rows, failures = asyncio.run(
        collect(
            targets,
            lambda: load_profile(args.profile),
            lambda profile, provider, model: _run_one(profile, jd_text, provider, model),
        )
    )

    for row in rows:
        print(
            f"{row.provider}:{row.model}  {row.verdict}  calls={row.llm_calls} "
            f"in={row.input_tokens} out={row.output_tokens} "
            f"invented_project_titles={len(row.invented_project_titles)} "
            f"unchecked_project_entries={row.unchecked_project_entries}"
        )

    for failure in failures:
        print(format_failure(failure))

    args.out.write_text(json.dumps(ledger_document(rows, failures), indent=2), encoding="utf-8")
    print(f"wrote {args.out}")
    return exit_code(failures)


if __name__ == "__main__":
    sys.exit(main())
