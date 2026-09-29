"""What a test fixture does when Postgres or Redis is not reachable.

Locally that is a skip: a contributor without `docker compose up -d db redis` still gets the unit
suite. In CI it must be a failure. A skip there turns a broken service container into a green run
with the whole database suite silently missing, which is worse than no CI at all, because it looks
like a pass.
"""

from __future__ import annotations

import os
from typing import NoReturn

import pytest

REQUIRE_SERVICES_ENV = "RHAPTO_TEST_REQUIRE_SERVICES"


def services_required() -> bool:
    """Exactly "1" turns it on. Anything else, including "true" or "0", leaves the local default."""
    return os.environ.get(REQUIRE_SERVICES_ENV, "").strip() == "1"


def service_unreachable(message: str) -> NoReturn:
    """Skip the test (local default) or fail it (CI, with RHAPTO_TEST_REQUIRE_SERVICES=1)."""
    if services_required():
        pytest.fail(f"{message} ({REQUIRE_SERVICES_ENV}=1, so this is a failure, not a skip)")
    pytest.skip(message)
