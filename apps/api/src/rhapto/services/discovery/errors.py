from __future__ import annotations


class SourceError(Exception):
    """A source request failed; recorded on the poll run, never fatal for the whole poll."""
