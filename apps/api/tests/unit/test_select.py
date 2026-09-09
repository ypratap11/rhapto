from pathlib import Path

import pytest

from rhapto.engine.providers.fake import FakeEmbeddingProvider
from rhapto.engine.select import (
    Selection,
    SelectionConfig,
    block_text,
    cosine,
    keyword_matches,
    select_blocks,
)
from rhapto.engine.types import Profile
from rhapto.models.jd_extract import JDExtract
from rhapto.models.profile.bases import ResumeBase
from rhapto.models.profile.blocks import Block, Visibility
from rhapto.models.profile.tracks import Track
from rhapto.profile.loader import load_profile


@pytest.fixture
def profile(demo_profile_dir: Path) -> Profile:
    return load_profile(demo_profile_dir)


@pytest.fixture
def extract() -> JDExtract:
    return JDExtract(
        company="ExampleCo",
        title="Data Platform Program Manager",
        must_have=["Snowflake migration", "program management across teams"],
        nice_to_have=["warehouse cost optimisation"],
        keywords=["Snowflake", "migration", "data platform", "program manager", "warehouse"],
    )


def test_cosine_basics() -> None:
    assert cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert cosine([0.0, 0.0], [1.0, 0.0]) == 0.0


def test_keyword_matches_whole_words_only() -> None:
    assert keyword_matches("ai", "hands-on AI product work")
    assert not keyword_matches("ai", "send an email to the team")
    assert not keyword_matches("program", "worked as a programmer")
    assert keyword_matches("data platform", "led the data-platform team")
    assert keyword_matches("data-platform", "led the data platform team")
    assert not keyword_matches("", "anything")


def test_block_text_joins_fields() -> None:
    block = Block(
        id="b",
        type="achievement",
        org="Acme",
        content="Did X.",
        metric="12 things",
        tags=["a", "b"],
    )
    assert block_text(block) == "Acme Did X. 12 things a b"


async def test_ranks_relevant_blocks_higher(profile: Profile, extract: JDExtract) -> None:
    selection = await select_blocks(
        extract, profile, profile.get_track("data-pm"), FakeEmbeddingProvider()
    )
    assert isinstance(selection, Selection)
    assert selection.scores["acme-migration"] > selection.scores["cred-pmp"]
    assert "acme-migration" in selection.block_ids
    assert selection.requirements_text.startswith("Snowflake migration")


async def test_orders_by_type_then_score(profile: Profile, extract: JDExtract) -> None:
    selection = await select_blocks(
        extract, profile, profile.get_track("data-pm"), FakeEmbeddingProvider()
    )
    types = [profile.block_map()[bid].type for bid in selection.block_ids]
    assert types == sorted(
        types, key=["role", "achievement", "project", "skill", "credential"].index
    )


async def test_top_k_limits_per_type(profile: Profile, extract: JDExtract) -> None:
    config = SelectionConfig(
        top_k={"role": 1, "achievement": 0, "project": 0, "skill": 0, "credential": 0}
    )
    selection = await select_blocks(
        extract, profile, profile.get_track("data-pm"), FakeEmbeddingProvider(), config
    )
    assert selection.block_ids == ["acme-data-pm"]


async def test_visibility_hard_excludes_before_ranking(extract: JDExtract) -> None:
    hidden = Block(
        id="agency-secret",
        type="achievement",
        content="Snowflake migration for a client",
        visibility=Visibility(exclude_when=["agency"]),
    )
    visible = Block(id="open", type="achievement", content="Snowflake migration")
    track = Track(id="t", name="T", resume_base="all")
    profile = Profile(
        blocks=[hidden, visible],
        tracks=[track],
        bases=[ResumeBase(id="all", name="All", block_ids=["agency-secret", "open"])],
        guardrails=[],
    )
    tagged = extract.model_copy(update={"context_tags": ["agency"]})
    selection = await select_blocks(tagged, profile, track, FakeEmbeddingProvider())
    assert selection.excluded_block_ids == ["agency-secret"]
    assert "agency-secret" not in selection.block_ids and "agency-secret" not in selection.scores
    assert selection.block_ids == ["open"]


async def test_restricts_to_track_base(profile: Profile, extract: JDExtract) -> None:
    narrow = profile.model_copy(
        update={
            "bases": [
                ResumeBase(id="data-pm", name="N", block_ids=["cred-pmp"]),
                profile.bases[1],
            ]
        }
    )
    selection = await select_blocks(
        extract, narrow, narrow.get_track("data-pm"), FakeEmbeddingProvider()
    )
    assert selection.block_ids == ["cred-pmp"]


async def test_empty_candidates(extract: JDExtract) -> None:
    track = Track(id="t", name="T", resume_base="empty")
    profile = Profile(
        blocks=[],
        tracks=[track],
        bases=[ResumeBase(id="empty", name="E", block_ids=[])],
        guardrails=[],
    )
    selection = await select_blocks(extract, profile, track, FakeEmbeddingProvider())
    assert selection.block_ids == [] and selection.scores == {}
