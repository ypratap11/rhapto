from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
DEMO_PROFILE = REPO_ROOT / "profile.example"


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def demo_profile_dir() -> Path:
    return DEMO_PROFILE
