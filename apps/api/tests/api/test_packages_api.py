import io
import zipfile
from typing import Any

import httpx
import pytest
from helpers import bullet, demo_extract, demo_resume

from rhapto.engine.compose import ComposeOutput

JD = "ExampleCo seeks a Data Platform Program Manager to lead our Snowflake migration. " * 3


def good_output() -> dict[str, Any]:
    resume = demo_resume()
    return ComposeOutput(
        summary=resume.summary,
        sections=resume.sections,
        cover_note="Dear team, " + "word " * 130,
        change_log="Emphasised migration.",
        answers={"why_this_company": "Data."},
    ).model_dump(mode="json")


async def _tailored(client: httpx.AsyncClient, fake_llm) -> tuple[str, str]:  # type: ignore[no-untyped-def]
    fake_llm.script(demo_extract(), good_output())
    job_id = str((await client.post("/api/v1/jobs", json={"jd_text": JD})).json()["id"])
    task = (await client.post(f"/api/v1/jobs/{job_id}/tailor", json={})).json()
    assert task["status"] == "succeeded", task
    return job_id, str(task["result_ref"])


@pytest.mark.usefixtures("imported_profile")
async def test_list_and_get(client: httpx.AsyncClient, fake_llm) -> None:  # type: ignore[no-untyped-def]
    job_id, package_id = await _tailored(client, fake_llm)
    listed = (await client.get(f"/api/v1/jobs/{job_id}/packages")).json()
    assert [p["version"] for p in listed] == [1] and listed[0]["id"] == package_id
    package = (await client.get(f"/api/v1/packages/{package_id}")).json()
    assert (
        package["status"] == "draft" and package["has_docx"] is True and package["has_pdf"] is False
    )
    assert (
        package["resume"]["header"]["name"] == "Maya Chen"
        and package["guardrail_report"]["passed"] is True
    )
    assert package["jd_extract"]["company"] == "ExampleCo" and package["llm_calls"] == 2


@pytest.mark.usefixtures("imported_profile")
async def test_patch_creates_new_validated_version(
    client: httpx.AsyncClient, fake_llm, enqueuer
) -> None:  # type: ignore[no-untyped-def]
    job_id, package_id = await _tailored(client, fake_llm)
    resume = (await client.get(f"/api/v1/packages/{package_id}")).json()["resume"]
    resume["sections"][0]["entries"][0]["bullets"][0]["text"] = (
        "Led cross-functional delivery of the customer data platform across 4 teams, on time."
    )
    patched = await client.patch(f"/api/v1/packages/{package_id}", json={"resume": resume})
    assert patched.status_code == 201, patched.text
    new = patched.json()
    assert (
        new["version"] == 2 and new["parent_package_id"] == package_id and new["status"] == "draft"
    )
    assert (
        new["llm_calls"] == 0
        and new["has_docx"] is True
        and new["cover_note"].startswith("Dear team")
    )
    assert [p["version"] for p in (await client.get(f"/api/v1/jobs/{job_id}/packages")).json()] == [
        1,
        2,
    ]
    assert ("render_package_pdf", {"package_id": new["id"]}) in enqueuer.calls


@pytest.mark.usefixtures("imported_profile")
async def test_patch_with_invented_metric_is_blocked(client: httpx.AsyncClient, fake_llm) -> None:  # type: ignore[no-untyped-def]
    _, package_id = await _tailored(client, fake_llm)
    resume = (await client.get(f"/api/v1/packages/{package_id}")).json()["resume"]
    resume["sections"][0]["entries"][0]["bullets"][1] = bullet(
        "Cut warehouse cost 25%.", "acme-migration"
    ).model_dump()
    new = (await client.patch(f"/api/v1/packages/{package_id}", json={"resume": resume})).json()
    assert new["status"] == "blocked"
    assert {v["rule"] for v in new["guardrail_report"]["violations"]} == {"no-unverified-metrics"}
    assert new["has_docx"] is True  # rendered for review; only orphan bullets suppress the DOCX


@pytest.mark.usefixtures("imported_profile")
async def test_patch_with_orphan_bullet_has_no_docx(client: httpx.AsyncClient, fake_llm) -> None:  # type: ignore[no-untyped-def]
    _, package_id = await _tailored(client, fake_llm)
    resume = (await client.get(f"/api/v1/packages/{package_id}")).json()["resume"]
    resume["summary"] = [bullet("Made up.", "ghost").model_dump()]
    new = (await client.patch(f"/api/v1/packages/{package_id}", json={"resume": resume})).json()
    assert new["status"] == "blocked" and new["has_docx"] is False
    assert any(v["rule"] == "provenance" for v in new["guardrail_report"]["violations"])
    assert (await client.get(f"/api/v1/packages/{new['id']}/files/resume.docx")).status_code == 404


@pytest.mark.usefixtures("imported_profile")
async def test_download_zip_and_files(client: httpx.AsyncClient, fake_llm) -> None:  # type: ignore[no-untyped-def]
    _, package_id = await _tailored(client, fake_llm)
    download = await client.get(f"/api/v1/packages/{package_id}/download")
    assert download.status_code == 200 and download.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(download.content)) as zf:
        assert set(zf.namelist()) == {"resume.docx", "cover-note.md", "package.json"}
        assert b'"version": 1' in zf.read("package.json")
    docx = await client.get(f"/api/v1/packages/{package_id}/files/resume.docx")
    assert docx.status_code == 200 and docx.content[:2] == b"PK"
    assert (await client.get(f"/api/v1/packages/{package_id}/files/resume.pdf")).status_code == 404
    assert (await client.get(f"/api/v1/packages/{package_id}/files/evil.txt")).status_code == 422


async def test_unknown_package_404(client: httpx.AsyncClient) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    assert (await client.get(f"/api/v1/packages/{missing}")).status_code == 404
    assert (await client.get(f"/api/v1/jobs/{missing}/packages")).status_code == 404
