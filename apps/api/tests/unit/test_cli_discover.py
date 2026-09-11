import json
from pathlib import Path

from typer.testing import CliRunner

from rhapto.cli import main as cli
from rhapto.services.discovery.http import FakeDiscoveryHttp

runner = CliRunner()


def test_discover_lists_scored_postings(monkeypatch, demo_profile_dir: Path) -> None:
    fixtures = Path(__file__).parent.parent / "fixtures" / "discovery"
    routes = json.loads((fixtures / "greenhouse.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(cli, "build_discovery_http", lambda settings: FakeDiscoveryHttp(routes))
    result = runner.invoke(
        cli.app,
        [
            "discover",
            "--profile",
            str(demo_profile_dir),
            "--source",
            "greenhouse",
            "--board",
            "exampleco",
            "--embedder",
            "fake",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    rows = json.loads(result.output)
    assert {r["title"] for r in rows} == {"Data Platform Program Manager", "AI Product Manager"}
    assert all({"fit", "track", "url", "company"} <= set(r) for r in rows)
    assert rows == sorted(rows, key=lambda r: -r["fit"])


def test_discover_reports_source_failure(monkeypatch, demo_profile_dir: Path) -> None:
    from rhapto.services.discovery.sources.base import SourceError

    monkeypatch.setattr(
        cli,
        "build_discovery_http",
        lambda settings: FakeDiscoveryHttp({"greenhouse.io": SourceError("HTTP 500")}),
    )
    result = runner.invoke(
        cli.app,
        [
            "discover",
            "--profile",
            str(demo_profile_dir),
            "--source",
            "greenhouse",
            "--board",
            "exampleco",
            "--embedder",
            "fake",
        ],
    )
    assert result.exit_code == 1 and "HTTP 500" in result.output


def test_score_prints_breakdown(tmp_path: Path, demo_profile_dir: Path) -> None:
    jd = tmp_path / "jd.txt"
    jd.write_text(
        "Data Program Manager to lead the analytics data platform and ETL migration.",
        encoding="utf-8",
    )
    result = runner.invoke(
        cli.app,
        ["score", "--jd", str(jd), "--profile", str(demo_profile_dir), "--embedder", "fake"],
    )
    assert result.exit_code == 0, result.output
    assert "data-pm" in result.output and "ai-pm" in result.output
