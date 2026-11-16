from __future__ import annotations

import ast
from pathlib import Path

import rhapto.allowlist as allowlist
from rhapto.api import auth


def test_auth_reexports_the_same_function() -> None:
    assert auth.is_allowed_email is allowlist.is_allowed_email


def test_allowlist_module_has_no_api_or_web_framework_imports() -> None:
    tree = ast.parse(Path(allowlist.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    banned = ("rhapto.api", "fastapi", "httpx", "jwt")
    assert not [m for m in imported if m.startswith(banned)]
