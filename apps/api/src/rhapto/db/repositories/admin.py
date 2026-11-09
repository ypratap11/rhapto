"""Owner-only admin reads and writes. This is the only place cross-user SQL lives, and only the
admin router (`rhapto.api.routers.admin`) may import it; the `admin-reads-are-admin-only`
import-linter contract enforces that.

Nothing here selects `answers`, `tasks.error` or `llm_settings` for a response.
"""

from __future__ import annotations

from rhapto.db import models  # noqa: F401
