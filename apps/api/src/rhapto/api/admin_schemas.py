from __future__ import annotations

from pydantic import BaseModel


class AdminSessionOut(BaseModel):
    ok: bool
