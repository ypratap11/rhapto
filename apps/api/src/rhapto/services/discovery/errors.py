from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Quota:
    """Vendor rate-limit state parsed from the allowlisted response headers."""

    limit: int | None
    remaining: int | None
    reset_seconds: int | None


class SourceError(Exception):
    """A source request failed; recorded on the poll run, never fatal for the whole poll."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class RateLimited(SourceError):
    """The vendor answered HTTP 429. Never retried; carries the parsed quota when present."""

    def __init__(
        self, message: str, *, status: int | None = 429, quota: Quota | None = None
    ) -> None:
        super().__init__(message, status=status)
        self.quota = quota
