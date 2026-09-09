from pathlib import Path

import pytest
import yaml

from rhapto.engine.types import ProfileError
from rhapto.profile.loader import dump_profile, load_profile


def test_loads_demo_profile(demo_profile_dir: Path) -> None:
    profile = load_profile(demo_profile_dir)
    assert {b.id for b in profile.blocks} == {
        "acme-data-pm",
        "acme-migration",
        "side-llm-tool",
        "cred-pmp",
    }
    assert [t.id for t in profile.tracks] == ["data-pm", "ai-pm"]
    assert profile.answers["name"] == "Maya Chen"
    assert profile.watchlist[0].company == "ExampleCo"
    assert {g.rule for g in profile.guardrails} == {
        "no-unverified-metrics",
        "no-invented-entities",
        "date-consistency",
    }


def test_synthesizes_bases_when_missing(demo_profile_dir: Path) -> None:
    profile = load_profile(demo_profile_dir)
    assert {b.id for b in profile.bases} == {"data-pm", "ai-pm"}
    base = profile.base_for(profile.get_track("ai-pm"))
    assert set(base.block_ids) == {b.id for b in profile.blocks}


def test_get_track_defaults_to_first(demo_profile_dir: Path) -> None:
    profile = load_profile(demo_profile_dir)
    assert profile.get_track(None).id == "data-pm"
    with pytest.raises(ProfileError, match="unknown track"):
        profile.get_track("nope")


def test_missing_blocks_file(tmp_path: Path) -> None:
    (tmp_path / "tracks.yaml").write_text("tracks: []\n", encoding="utf-8")
    with pytest.raises(ProfileError, match="blocks.yaml"):
        load_profile(tmp_path)


def test_duplicate_block_id(tmp_path: Path) -> None:
    (tmp_path / "blocks.yaml").write_text(
        yaml.safe_dump(
            {
                "blocks": [
                    {"id": "a", "type": "role", "content": "x"},
                    {"id": "a", "type": "role", "content": "y"},
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "tracks.yaml").write_text(
        yaml.safe_dump({"tracks": [{"id": "t", "name": "T", "resume_base": "t"}]}), encoding="utf-8"
    )
    with pytest.raises(ProfileError, match="duplicate block id"):
        load_profile(tmp_path)


def test_base_referencing_unknown_block(tmp_path: Path) -> None:
    (tmp_path / "blocks.yaml").write_text(
        yaml.safe_dump({"blocks": [{"id": "a", "type": "role", "content": "x"}]}), encoding="utf-8"
    )
    (tmp_path / "tracks.yaml").write_text(
        yaml.safe_dump({"tracks": [{"id": "t", "name": "T", "resume_base": "b"}]}), encoding="utf-8"
    )
    (tmp_path / "bases.yaml").write_text(
        yaml.safe_dump({"bases": [{"id": "b", "name": "B", "block_ids": ["a", "ghost"]}]}),
        encoding="utf-8",
    )
    with pytest.raises(ProfileError, match="ghost"):
        load_profile(tmp_path)


def test_unparseable_period_names_file(tmp_path: Path) -> None:
    (tmp_path / "blocks.yaml").write_text(
        yaml.safe_dump(
            {"blocks": [{"id": "a", "type": "role", "content": "x", "period": "Spring 2020"}]}
        ),
        encoding="utf-8",
    )
    (tmp_path / "tracks.yaml").write_text("tracks: []\n", encoding="utf-8")
    with pytest.raises(ProfileError, match="blocks.yaml"):
        load_profile(tmp_path)


def test_invalid_yaml_shape_names_file(tmp_path: Path) -> None:
    (tmp_path / "blocks.yaml").write_text(
        "blocks: [{id: a, type: hobby, content: x}]\n", encoding="utf-8"
    )
    (tmp_path / "tracks.yaml").write_text("tracks: []\n", encoding="utf-8")
    with pytest.raises(ProfileError, match="blocks.yaml"):
        load_profile(tmp_path)


def test_default_guardrails_when_file_missing(tmp_path: Path) -> None:
    (tmp_path / "blocks.yaml").write_text(
        yaml.safe_dump({"blocks": [{"id": "a", "type": "role", "content": "x"}]}), encoding="utf-8"
    )
    (tmp_path / "tracks.yaml").write_text(
        yaml.safe_dump({"tracks": [{"id": "t", "name": "T", "resume_base": "t"}]}), encoding="utf-8"
    )
    profile = load_profile(tmp_path)
    assert {g.rule for g in profile.guardrails} == {
        "no-unverified-metrics",
        "no-invented-entities",
        "date-consistency",
        "attribution",
        "visibility-context",
    }


def test_dump_round_trip(demo_profile_dir: Path, tmp_path: Path) -> None:
    profile = load_profile(demo_profile_dir)
    dump_profile(profile, tmp_path)
    assert {p.name for p in tmp_path.iterdir()} == {
        "blocks.yaml",
        "tracks.yaml",
        "bases.yaml",
        "guardrails.yaml",
        "answers.yaml",
        "watchlist.yaml",
    }
    assert load_profile(tmp_path) == profile
