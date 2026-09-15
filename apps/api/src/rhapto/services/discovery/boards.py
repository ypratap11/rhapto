"""Recognising an ATS board from a job URL, so a result can add its company to the watchlist."""

from __future__ import annotations

import re
from urllib.parse import urlparse

SLUG = re.compile(r"^[A-Za-z0-9._-]+$")
WORKDAY_HOST = ".myworkdayjobs.com"

_GREENHOUSE_HOSTS = ("boards.greenhouse.io", "job-boards.greenhouse.io")


def board_from_url(url: str) -> tuple[str, str] | None:
    """`(source, board)` for a recognised ATS posting URL, else None.

    Hosts are compared in full and lower-cased, so `evil.myworkdayjobs.com.attacker.net` is not a
    Workday tenant; slugs must be a single path segment of `[A-Za-z0-9._-]`.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    segments = [s for s in parsed.path.split("/") if s]
    if not host:
        return None
    if host in _GREENHOUSE_HOSTS and segments and SLUG.match(segments[0]):
        return ("greenhouse", segments[0])
    if host == "jobs.lever.co" and segments and SLUG.match(segments[0]):
        return ("lever", segments[0])
    if host == "jobs.ashbyhq.com" and segments and SLUG.match(segments[0]):
        return ("ashby", segments[0])
    if host.endswith(WORKDAY_HOST):
        prefix = host[: -len(WORKDAY_HOST)]
        if not prefix or not SLUG.match(prefix):
            return None
        # /wday/cxs/<tenant>/<site>/... is the JSON API; /<lang>/<site>/... is the human page.
        if len(segments) >= 4 and segments[0] == "wday" and segments[1] == "cxs":
            tenant, site = segments[2], segments[3]
        elif len(segments) >= 2:
            tenant, site = prefix, segments[1]
        else:
            return None
        if SLUG.match(tenant) and SLUG.match(site):
            return ("workday", f"{tenant}/{site}")
    return None
