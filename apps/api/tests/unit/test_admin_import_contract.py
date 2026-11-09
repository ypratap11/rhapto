"""The admin repository holds cross-user SQL; only the admin router may import it."""

from __future__ import annotations

import ast
import configparser
import shutil
import subprocess
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2]
SRC = API_ROOT / "src" / "rhapto"
CONTRACT = "admin-reads-are-admin-only"
ALLOWED_IGNORE = "rhapto.api.routers.admin -> rhapto.db.repositories.admin"


def _lint(cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from importlinter.cli import lint_imports_command as m; "
            "sys.argv = ['lint-imports', '--config', '.importlinter']; m()",
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _lines(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]


def test_contract_is_declared() -> None:
    parser = configparser.ConfigParser()
    parser.read(API_ROOT / ".importlinter")
    section = f"importlinter:contract:{CONTRACT}"
    assert parser.has_section(section)
    assert parser.get(section, "type") == "forbidden"
    assert sorted(_lines(parser.get(section, "source_modules"))) == [
        "rhapto.api",
        "rhapto.services",
        "rhapto.worker",
    ]
    assert _lines(parser.get(section, "forbidden_modules")) == ["rhapto.db.repositories.admin"]
    if parser.has_option(section, "ignore_imports"):
        assert _lines(parser.get(section, "ignore_imports")) == [ALLOWED_IGNORE]


def test_contract_breaks_when_a_service_imports_the_admin_repo(tmp_path: Path) -> None:
    shutil.copytree(SRC, tmp_path / "rhapto", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(API_ROOT / ".importlinter", tmp_path / ".importlinter")
    trial = tmp_path / "rhapto" / "services" / "trial.py"
    trial.write_text(
        trial.read_text(encoding="utf-8") + "\nfrom rhapto.db.repositories import admin  # noqa\n",
        encoding="utf-8",
    )
    result = _lint(tmp_path)
    assert result.returncode != 0
    assert CONTRACT in result.stdout + result.stderr


def test_contract_passes_on_the_real_tree() -> None:
    result = _lint(API_ROOT)
    assert result.returncode == 0, result.stdout + result.stderr


def test_only_admin_router_imports_admin_repo() -> None:
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(SRC).as_posix()
        if rel in ("api/routers/admin.py", "db/repositories/admin.py"):
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                names = [a.name for a in node.names]
                if mod == "rhapto.db.repositories.admin" or (
                    mod == "rhapto.db.repositories" and "admin" in names
                ):
                    offenders.append(rel)
            elif isinstance(node, ast.Import):
                if any(a.name == "rhapto.db.repositories.admin" for a in node.names):
                    offenders.append(rel)
    assert offenders == []
