from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "rhapto"


def test_feedback_router_docstring_points_to_admin_repo() -> None:
    text = (SRC / "api" / "routers" / "feedback.py").read_text(encoding="utf-8")
    assert "repositories/admin.py" in text.split('"""')[1]


def test_feedback_repo_points_to_admin_repo() -> None:
    doc = (SRC / "db" / "repositories" / "feedback.py").read_text(encoding="utf-8").split('"""')[1]
    assert "this module's one cross-user read" in doc
    assert "repositories/admin.py" in doc
