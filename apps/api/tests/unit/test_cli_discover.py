import asyncio
import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from rhapto.cli import main as cli
from rhapto.engine.providers.fake import FakeEmbeddingProvider
from rhapto.engine.scoring import score_job, track_text
from rhapto.profile.loader import load_profile
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


def test_score_no_location_preference_skips_unknown_penalty(
    tmp_path: Path, demo_profile_dir: Path
) -> None:
    """Regression guard for item 6 (I3): `cli/main.py`'s `score` command must not apply the
    'unknown' location-tier penalty to a user who has expressed no location preference at all.

    `score_job` defaults `has_location_preference` to True, and the CLI's `score` command used to
    call it without passing the argument -- so it always took that default and applied the 0.90
    'unknown' multiplier even when `location_preference_from_answers` reports no terms. This test
    uses a profile with no `answers.yaml` (so `answers == {}` and there is no location preference)
    and checks the printed fit matches the no-penalty (multiplier 1.0) score, not the penalised one.
    """
    profile_dir = tmp_path / "profile"
    shutil.copytree(demo_profile_dir, profile_dir)
    (profile_dir / "answers.yaml").unlink()

    jd = tmp_path / "jd.txt"
    jd.write_text(
        "Data Program Manager to lead the analytics data platform and ETL migration.",
        encoding="utf-8",
    )
    result = runner.invoke(
        cli.app,
        ["score", "--jd", str(jd), "--profile", str(profile_dir), "--embedder", "fake"],
    )
    assert result.exit_code == 0, result.output

    loaded = load_profile(profile_dir)
    assert loaded.answers == {}
    text = jd.read_text(encoding="utf-8")
    embedder = FakeEmbeddingProvider(dimensions=384)

    async def compute_expected() -> int:
        vectors = await embedder.embed([track_text(t) for t in loaded.tracks] + [text])
        track_vectors = {t.id: v for t, v in zip(loaded.tracks, vectors[:-1], strict=True)}
        title = text.strip().splitlines()[0][:200]
        scores = score_job(
            title,
            text,
            vectors[-1],
            loaded.tracks,
            track_vectors,
            has_location_preference=False,
        )
        return next(s.fit_score for s in scores if s.track_id == "data-pm")

    expected_fit = asyncio.run(compute_expected())
    line = next(line for line in result.output.splitlines() if line.startswith("data-pm"))
    printed_fit = int(line.split("fit=")[1].split()[0])
    assert printed_fit == expected_fit
