from __future__ import annotations

import hashlib
import re


def dedupe_hash(jd_text: str) -> str:
    """SHA-256 hex digest of the lowercased, whitespace-collapsed first 4000 characters of jd_text."""
    normalized = re.sub(r"\s+", " ", jd_text.strip().lower())[:4000]
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
