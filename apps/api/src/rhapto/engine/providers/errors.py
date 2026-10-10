from __future__ import annotations

from typing import Literal

from rhapto.engine.types import EngineError

#: auth: the key was not accepted (401/403, invalid, expired, revoked). quota: its allowance is spent
#: (insufficient credit, billing). The worker words each differently for the user.
KeyFailureKind = Literal["auth", "quota"]


class ProviderAuthError(EngineError):
    """The provider rejected the key (401/403/invalid key) or the account's allowance is spent.

    Carries the SDK's own message: it names the real problem (wrong key, project without access,
    exhausted quota) better than anything this layer could invent, and the API surfaces it as-is.
    Everything else an SDK raises -- timeouts, 5xx, bad requests -- is a plain `EngineError`, so
    callers can tell "the user must fix their credentials" from "try again".
    """

    def __init__(self, provider: str, message: str, *, kind: KeyFailureKind = "auth") -> None:
        super().__init__(message)
        self.provider = provider
        self.kind = kind


def mentions_quota(message: str) -> bool:
    """True when a 429 is about a spent allowance rather than a momentary rate limit.

    Only for SDKs that expose no machine-readable error code (Gemini); OpenAI's `insufficient_quota`
    code is read directly instead. Deliberately narrow: OpenAI's ordinary rate-limit text points at
    the billing page, so matching words like "billing" turned retryable limits into terminal
    credential errors.
    """
    return "quota" in message.lower()
