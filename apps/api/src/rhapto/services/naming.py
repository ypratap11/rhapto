from __future__ import annotations

import re

FALLBACK = "Resume"


def download_basename(name: str | None) -> str:
    """Candidate name as a safe filename stem: runs of non-alphanumerics become `_`; empty -> Resume."""
    stem = re.sub(r"[^A-Za-z0-9]+", "_", name or "").strip("_")
    return stem or FALLBACK
