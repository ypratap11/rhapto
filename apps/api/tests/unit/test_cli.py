import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from docx import Document
from helpers import bullet, demo_extract, demo_resume
from helpers_docx import build_fixture_docx
from typer.testing import CliRunner

from rhapto.cli import main as cli
from rhapto.engine.compose import AnswerItem, ComposeOutput
from rhapto.engine.providers.fake import FakeEmbeddingProvider, FakeLLMProvider
from rhapto.engine.tune import ProposedEdit, TuneOutput

runner = CliRunner()
JD = "ExampleCo seeks a Data Platform Program Manager to lead our Snowflake migration."


def _good() -> dict[str, Any]:
    resume = demo_resume()
    return ComposeOutput(
        summary=resume.summary,
        sections=resume.sections,
        cover_note="Dear team.",
        change_log="Emphasised migration.",
        answers=[AnswerItem(key="why_this_company", value="Data.")],
    ).model_dump(mode="json")


def _bad() -> dict[str, Any]:
    output = _good()
    output["sections"][0]["entries"][0]["bullets"][1] = bullet(
        "Cut warehouse cost 25%.", "acme-migration"
    ).model_dump()
    return output


@pytest.fixture
def workspace(tmp_path: Path, demo_profile_dir: Path) -> Path:
    shutil.copytree(demo_profile_dir, tmp_path / "profile")
    (tmp_path / "jd.txt").write_text(JD, encoding="utf-8")
    return tmp_path


def _patch_providers(monkeypatch: pytest.MonkeyPatch, responses: list[Any]) -> FakeLLMProvider:
    llm = FakeLLMProvider(responses)
    monkeypatch.setattr(
        cli,
        "build_providers",
        lambda settings: cli.Providers(llm=llm, embedder=FakeEmbeddingProvider()),
    )
    return llm


def test_slugify() -> None:
    assert cli.slugify("ExampleCo, Inc.") == "exampleco-inc"
    assert cli.slugify("Data Platform  Program Manager") == "data-platform-program-manager"
    assert cli.slugify("") == "untitled"


def test_tailor_writes_package(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_providers(monkeypatch, [demo_extract(), _good()])
    result = runner.invoke(
        cli.app,
        [
            "tailor",
            "--jd",
            str(workspace / "jd.txt"),
            "--profile",
            str(workspace / "profile"),
            "--out",
            str(workspace / "out"),
            "--no-pdf",
        ],
    )
    assert result.exit_code == 0, result.output
    target = workspace / "out" / "exampleco-data-platform-program-manager"
    assert {p.name for p in target.iterdir()} == {"resume.docx", "cover-note.md", "package.json"}
    package = json.loads((target / "package.json").read_text(encoding="utf-8"))
    assert package["status"] == "draft" and package["llm_calls"] == 2
    assert (target / "cover-note.md").read_text(encoding="utf-8").strip() == "Dear team."
    assert "guardrails: passed" in result.output and "extract" in result.output


def test_tailor_blocked_exits_3(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_providers(monkeypatch, [demo_extract(), _bad(), _bad()])
    result = runner.invoke(
        cli.app,
        [
            "tailor",
            "--jd",
            str(workspace / "jd.txt"),
            "--profile",
            str(workspace / "profile"),
            "--out",
            str(workspace / "out"),
            "--no-pdf",
        ],
    )
    assert result.exit_code == 3, result.output
    assert "no-unverified-metrics" in result.output and "25%" in result.output
    assert (workspace / "out" / "exampleco-data-platform-program-manager" / "package.json").exists()


def test_tailor_with_track_and_feedback(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    llm = _patch_providers(monkeypatch, [demo_extract(), _good()])
    result = runner.invoke(
        cli.app,
        [
            "tailor",
            "--jd",
            str(workspace / "jd.txt"),
            "--profile",
            str(workspace / "profile"),
            "--out",
            str(workspace / "out"),
            "--no-pdf",
            "--track",
            "ai-pm",
            "--feedback",
            "lean on AI",
        ],
    )
    assert result.exit_code == 0, result.output
    package = json.loads(
        (workspace / "out" / "exampleco-data-platform-program-manager" / "package.json").read_text(
            encoding="utf-8"
        )
    )
    assert package["track_id"] == "ai-pm"
    assert "lean on AI" in llm.calls[1].messages[0].content


def test_tailor_document_switches_on_tune_mode(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clean_bullet = "Led the Snowflake migration for 12 teams, reducing warehouse cost 30%."
    (workspace / "resume.docx").write_bytes(build_fixture_docx())
    tune_output = TuneOutput(
        edits=[ProposedEdit(paragraph_id="p9", text=clean_bullet, reason="mirrors the JD")],
        cover_note="I have led Snowflake migrations end to end for platform teams.",
        change_log="Emphasised the migration.",
        answers=[AnswerItem(key="why_this_company", value="Data.")],
    ).model_dump(mode="json")
    _patch_providers(monkeypatch, [demo_extract(), tune_output])
    result = runner.invoke(
        cli.app,
        [
            "tailor",
            "--jd",
            str(workspace / "jd.txt"),
            "--profile",
            str(workspace / "profile"),
            "--document",
            str(workspace / "resume.docx"),
            "--out",
            str(workspace / "out"),
            "--no-pdf",
        ],
    )
    assert result.exit_code == 0, result.output
    target = workspace / "out" / "exampleco-data-platform-program-manager"
    assert {p.name for p in target.iterdir()} == {"resume.docx", "cover-note.md", "package.json"}
    texts = [p.text for p in Document(str(target / "resume.docx")).paragraphs]
    assert clean_bullet in texts
    package = json.loads((target / "package.json").read_text(encoding="utf-8"))
    assert package["mode"] == "tune"
    assert package["edits"] and package["edits"][0]["after"] == clean_bullet


def test_tailor_mode_tune_without_document_exits_2(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_providers(monkeypatch, [])
    result = runner.invoke(
        cli.app,
        [
            "tailor",
            "--jd",
            str(workspace / "jd.txt"),
            "--profile",
            str(workspace / "profile"),
            "--mode",
            "tune",
            "--no-pdf",
        ],
    )
    assert result.exit_code == 2, result.output


def test_tailor_bad_profile_exits_1(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_providers(monkeypatch, [])
    (workspace / "profile" / "blocks.yaml").write_text(
        "blocks: [{id: a, type: hobby, content: x}]\n", encoding="utf-8"
    )
    result = runner.invoke(
        cli.app,
        [
            "tailor",
            "--jd",
            str(workspace / "jd.txt"),
            "--profile",
            str(workspace / "profile"),
            "--no-pdf",
        ],
    )
    assert result.exit_code == 1 and "blocks.yaml" in result.output


def test_tailor_skips_pdf_when_soffice_missing(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_providers(monkeypatch, [demo_extract(), _good()])
    monkeypatch.setattr(cli, "soffice_available", lambda binary: False)
    result = runner.invoke(
        cli.app,
        [
            "tailor",
            "--jd",
            str(workspace / "jd.txt"),
            "--profile",
            str(workspace / "profile"),
            "--out",
            str(workspace / "out"),
        ],
    )
    assert result.exit_code == 0 and "PDF skipped" in result.output


def test_tailor_renders_pdf_when_available(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_providers(monkeypatch, [demo_extract(), _good()])
    monkeypatch.setattr(cli, "soffice_available", lambda binary: True)

    def fake_convert(
        docx_path: Path, out_dir: Path, binary: str = "soffice", timeout: int = 180
    ) -> Path:
        pdf = out_dir / "resume.pdf"
        pdf.write_bytes(b"%PDF")
        return pdf

    monkeypatch.setattr(cli, "convert_docx_to_pdf", fake_convert)
    result = runner.invoke(
        cli.app,
        [
            "tailor",
            "--jd",
            str(workspace / "jd.txt"),
            "--profile",
            str(workspace / "profile"),
            "--out",
            str(workspace / "out"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert (workspace / "out" / "exampleco-data-platform-program-manager" / "resume.pdf").exists()


def test_tailor_missing_jd_exits_1(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_providers(monkeypatch, [])
    result = runner.invoke(
        cli.app,
        [
            "tailor",
            "--jd",
            str(workspace / "missing.txt"),
            "--profile",
            str(workspace / "profile"),
            "--no-pdf",
        ],
    )
    assert result.exit_code == 1 and "not found" in result.output


def test_tailor_missing_api_key_exits_1(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from rhapto.config import Settings

    monkeypatch.setattr(cli, "get_settings", lambda: Settings(_env_file=None, anthropic_api_key=""))
    result = runner.invoke(
        cli.app,
        [
            "tailor",
            "--jd",
            str(workspace / "jd.txt"),
            "--profile",
            str(workspace / "profile"),
            "--no-pdf",
        ],
    )
    assert result.exit_code == 1 and "ANTHROPIC_API_KEY" in result.output


def test_build_providers_requires_api_key() -> None:
    from rhapto.config import Settings

    with pytest.raises(cli.typer.BadParameter, match="ANTHROPIC_API_KEY"):
        cli.build_providers(Settings(_env_file=None, anthropic_api_key=""))


def test_profile_validate(workspace: Path, demo_profile_dir: Path) -> None:
    ok = runner.invoke(cli.app, ["profile", "validate", str(demo_profile_dir)])
    assert ok.exit_code == 0 and "4 blocks" in ok.output and "2 tracks" in ok.output
    bad = runner.invoke(cli.app, ["profile", "validate", str(workspace / "nothing")])
    assert bad.exit_code == 1


def test_db_upgrade_and_profile_import_export_commands_exist() -> None:
    result = runner.invoke(cli.app, ["db", "--help"])
    assert result.exit_code == 0 and "upgrade" in result.output
    result = runner.invoke(cli.app, ["profile", "--help"])
    assert "import" in result.output and "export" in result.output


def test_db_upgrade_reports_an_unreachable_database(monkeypatch: pytest.MonkeyPatch) -> None:
    from rhapto.config import Settings

    monkeypatch.setenv("DATABASE_URL", "unused")  # restored on teardown
    monkeypatch.setattr(
        cli,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            database_url="postgresql+asyncpg://rhapto:sup3rsecret@127.0.0.1:1/rhapto",
        ),
    )
    result = runner.invoke(cli.app, ["db", "upgrade"])
    assert result.exit_code == 1
    assert "cannot reach the database" in result.output
    assert "docker compose up -d db redis" in result.output
    assert "sup3rsecret" not in result.output and "***" in result.output
