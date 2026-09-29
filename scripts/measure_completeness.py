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
it is safe to produce from a real profile. (A failed run prints its exception message, which is
not ledger content; check it before pasting it anywhere.)

Reading the output: `first pass failed: completeness` is a model that dropped a selected block.
`repaired (...)` means the one repair call restored it; `blocked after repair (...)` means it did
not. Both read `TailorResult.pre_repair_report`, not `llm_calls`, so a malformed-output retry is
never mistaken for a repair. `invented_project_titles` lists the ids of project blocks whose entry
title or role text is not made of words from the block it cites (the count is printed): no
guardrail validates a title, so this is the only place the U-1 risk (models inventing a title for
a project block with no role) shows up. Look the ids up in the profile to inspect them.
That repair-success rate, per model, is the number architecture
condition C6 says decides whether the deterministic entry skeleton (Phase 6) is needed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from rhapto.cli.main import build_providers
from rhapto.config import get_settings
from rhapto.engine.measurement import (
    final_rules,
    first_pass_rules,
    invented_project_titles,
    summarize_result,
)
from rhapto.engine.pipeline import tailor
from rhapto.engine.types import TailorRequest
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
    status: str
    llm_calls: int
    input_tokens: int
    output_tokens: int


async def _run_one(jd_text: str, profile_dir: Path, provider: str, model: str) -> MeasurementRow:
    providers = build_providers(get_settings(), provider, model)
    profile = load_profile(profile_dir)
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
        status=package.status,
        llm_calls=package.llm_calls,
        input_tokens=package.usage.input_tokens,
        output_tokens=package.usage.output_tokens,
    )


async def _run_all(
    jd_text: str, profile_dir: Path, targets: list[tuple[str, str]]
) -> list[MeasurementRow]:
    rows: list[MeasurementRow] = []
    for provider, model in targets:
        try:
            rows.append(await _run_one(jd_text, profile_dir, provider, model))
        except Exception as exc:
            print(f"{provider}:{model}  FAILED: {exc}")
    return rows


def _parse_target(parser: argparse.ArgumentParser, raw: str) -> tuple[str, str]:
    provider, sep, model = raw.partition(":")
    if not sep or not provider or not model:
        parser.error(
            f"--provider expects PROVIDER:MODEL (for example anthropic:claude-haiku-5), got {raw!r}"
        )
    return provider, model


def main() -> None:
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
    jd_text = args.jd.read_text(encoding="utf-8")
    rows = asyncio.run(_run_all(jd_text, args.profile, targets))

    for row in rows:
        print(
            f"{row.provider}:{row.model}  {row.verdict}  calls={row.llm_calls} "
            f"in={row.input_tokens} out={row.output_tokens} "
            f"invented_project_titles={len(row.invented_project_titles)}"
        )

    args.out.write_text(json.dumps([asdict(r) for r in rows], indent=2), encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
