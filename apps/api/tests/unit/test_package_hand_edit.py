"""Hand edits (PATCH, blocks mode) are not subject to `completeness` (controller ruling on final
review I-2): a block the user deletes is a deliberate choice, not a silent AI drop. Every other rule
still runs, and a failing report still yields no DOCX.

`_edited_blocks_version` is called directly with an in-memory parent, so this runs without Postgres;
the same path over HTTP is `test_patch_with_invented_metric_is_blocked` (CI).
"""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from helpers import bullet, demo_extract, demo_resume

from rhapto.api.routers import packages as router
from rhapto.engine.types import Profile
from rhapto.models.resume_document import ResumeDocument
from rhapto.profile.loader import load_profile


@pytest.fixture
def profile(demo_profile_dir: Path) -> Profile:
    return load_profile(demo_profile_dir)


def _parent(profile: Profile) -> Any:
    return SimpleNamespace(
        selection_block_ids=[*profile.block_map()],
        cover_note=None,
        track_id=profile.tracks[0].id,
    )


def _without_credentials() -> ResumeDocument:
    resume = demo_resume()
    resume.sections = [s for s in resume.sections if s.kind != "credentials"]
    return resume


async def test_a_hand_edit_that_removes_a_selected_credential_stays_draft_with_a_docx(
    profile: Profile,
) -> None:
    version = await router._edited_blocks_version(
        _parent(profile), profile, demo_extract(), _without_credentials()
    )
    assert version.report.passed is True, [v.model_dump() for v in version.report.violations]
    assert "completeness" not in version.report.rules_run
    assert version.docx.startswith(b"PK")  # a real DOCX was rendered


async def test_a_hand_edit_with_an_invented_metric_is_still_blocked_without_a_docx(
    profile: Profile,
) -> None:
    resume = _without_credentials()
    resume.sections[0].entries[0].bullets.append(bullet("Cut cost 37%.", "acme-migration"))
    version = await router._edited_blocks_version(_parent(profile), profile, demo_extract(), resume)
    assert version.report.passed is False
    assert any(v.rule == "no-unverified-metrics" for v in version.report.violations)
    assert version.docx == b""
