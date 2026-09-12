import httpx
from helpers_docx import build_fixture_docx

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


async def test_upload_get_delete_resume_document(client: httpx.AsyncClient) -> None:
    missing = await client.get("/api/v1/profile/resume-document")
    assert missing.status_code == 404
    files = {"file": ("Maya_Chen_Resume.docx", build_fixture_docx(), DOCX_MIME)}
    up = await client.post("/api/v1/profile/resume-document", files=files)
    assert up.status_code == 201, up.text
    body = up.json()
    assert body["filename"] == "Maya_Chen_Resume.docx"
    assert any(p["role"] == "summary" for p in body["document"]["paragraphs"])
    got = await client.get("/api/v1/profile/resume-document")
    assert got.status_code == 200 and got.json()["document"]["sections"]
    bad = await client.post(
        "/api/v1/profile/resume-document", files={"file": ("x.pdf", b"%PDF", "application/pdf")}
    )
    assert bad.status_code == 422
    gone = await client.delete("/api/v1/profile/resume-document")
    assert gone.status_code == 204
    assert (await client.get("/api/v1/profile/resume-document")).status_code == 404


async def test_second_upload_replaces_the_first(client: httpx.AsyncClient) -> None:
    data = build_fixture_docx()
    for name in ("first.docx", "second.docx"):
        up = await client.post(
            "/api/v1/profile/resume-document", files={"file": (name, data, DOCX_MIME)}
        )
        assert up.status_code == 201, up.text
    got = await client.get("/api/v1/profile/resume-document")
    assert got.status_code == 200 and got.json()["filename"] == "second.docx"


async def test_corrupt_docx_is_rejected(client: httpx.AsyncClient) -> None:
    bad = await client.post(
        "/api/v1/profile/resume-document",
        files={"file": ("broken.docx", b"not a zip at all", DOCX_MIME)},
    )
    assert bad.status_code == 422 and "docx" in bad.json()["detail"]
    assert (await client.get("/api/v1/profile/resume-document")).status_code == 404
