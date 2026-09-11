from __future__ import annotations

import hashlib
import re

_PAREN = re.compile(r"\([^)]*\)")


def normalize_title(title: str) -> str:
    base = _PAREN.sub(" ", title)
    base = base.split(" - ")[0].split(" – ")[0]
    return re.sub(r"\s+", " ", base).strip().lower()


def identity_hash(company: str, title: str, location: str | None) -> str:
    key = f"{company.strip().lower()}|{normalize_title(title)}|{(location or '').strip().lower()}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()
