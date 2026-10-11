"""JobCreate.url accepts only absolute http(s): the value is fetched server-side and later rendered
as a link, so javascript:/data:/file: must be rejected at the edge."""

import pytest
from pydantic import ValidationError

from rhapto.api.schemas import JobCreate


@pytest.mark.parametrize(
    "url",
    ["https://boards.example.com/jobs/1", "http://example.com/a?b=1", "  https://example.com/x  "],
)
def test_http_urls_are_accepted(url: str) -> None:
    assert JobCreate(url=url).url == url.strip()


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "JavaScript:alert(1)",
        "data:text/html,<script>1</script>",
        "file:///etc/passwd",
        "ftp://example.com/x",
        "/relative/path",
        "example.com/no-scheme",
        "https://",
    ],
)
def test_other_schemes_and_relative_urls_are_rejected(url: str) -> None:
    with pytest.raises(ValidationError):
        JobCreate(url=url)


def test_pasted_text_without_url_still_works() -> None:
    assert (
        JobCreate(
            jd_text="We are hiring a program manager to run data platform launches end to end."
        ).url
        is None
    )
