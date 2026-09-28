"""Every guardrail rule ships with something to do about it.

A blocked package says which rule fired, what it said and which bullet, and then stops. "Blocked" is
not an explanation, and a rule added without a remedy would put the product straight back there --
which is why this discovers the rules from the package rather than from a list someone has to
remember to update.

NOTE ON LOCATION. These are pure functions with no database and no HTTP, so `tests/unit/` is where
they belong by shape. They live under `tests/api/` because that is where the *gate* looks: the brief,
architecture condition C10 and every report use `uv run pytest tests/api tests/db`, this repository
has no CI, and a guard nothing runs is not a guard. What they assert is an API contract anyway --
`JobFilterId` is a wire type and the remedies are attached at response time.
"""

from __future__ import annotations

import importlib
import pkgutil

import rhapto.engine.guardrails as guardrails_package
from rhapto.engine.guardrails.registry import REMEDIES, remedies_for


def declared_rule_names() -> set[str]:
    """Every `RULE_NAME` constant in `rhapto.engine.guardrails`, found by walking the package.

    Discovered, not listed: a hard-coded list of the six rules would have to be updated by the same
    person who forgot the remedy, so it would not catch them.
    """
    names: set[str] = set()
    for module in pkgutil.iter_modules(guardrails_package.__path__):
        loaded = importlib.import_module(f"{guardrails_package.__name__}.{module.name}")
        rule = getattr(loaded, "RULE_NAME", None)
        if isinstance(rule, str):
            names.add(rule)
    return names


def test_every_rule_has_a_remedy() -> None:
    declared = declared_rule_names()
    assert declared, "no RULE_NAME constants found -- the discovery walk is broken, not the rules"
    assert set(REMEDIES) == declared, (
        f"rules with no remedy: {sorted(declared - set(REMEDIES))}; "
        f"remedies for no rule: {sorted(set(REMEDIES) - declared)}"
    )


def test_the_six_rules_this_build_ships_are_the_ones_expected() -> None:
    """Pinned by name as well as by count. Six rules exist; four of them are user-configurable
    (`RULES`), and `provenance` and `no-unverified-metrics` run unconditionally. A note saying "only
    5 rules exist" is imprecise -- 5 is the typical length of `rules_run`, not the number of rules.
    """
    assert declared_rule_names() == {
        "provenance",
        "no-unverified-metrics",
        "no-invented-entities",
        "date-consistency",
        "attribution",
        "visibility-context",
    }


def test_no_remedy_is_empty_or_a_restatement_of_the_rule_id() -> None:
    """A remedy has to tell the user what to DO. An empty string, or the rule id echoed back, would
    satisfy the coverage test above while shipping the same silence."""
    for rule, remedy in REMEDIES.items():
        assert remedy.strip(), rule
        assert remedy.strip().lower() != rule.lower(), rule
        # Long enough to be an instruction rather than a label.
        assert len(remedy) > 40, rule


def test_remedies_for_returns_only_the_rules_asked_about() -> None:
    subset = remedies_for(["provenance", "attribution"])
    assert set(subset) == {"provenance", "attribution"}


def test_remedies_for_skips_a_rule_it_does_not_know() -> None:
    """An unknown rule must be absent, not an empty string and not a KeyError: the panel renders the
    rule id, message and path for an absent key, and that fallback is what keeps an
    added-server-side-first rule visible instead of blanked out."""
    subset = remedies_for(["provenance", "some-future-rule"])
    assert set(subset) == {"provenance"}


def test_remedies_for_deduplicates_repeated_rules() -> None:
    """A report commonly holds several violations of one rule; the response carries one remedy."""
    subset = remedies_for(["provenance", "provenance", "provenance"])
    assert subset == {"provenance": REMEDIES["provenance"]}
