from __future__ import annotations

from rhapto.engine.types import EngineError

# Words that turn a 429 into a credentials problem rather than a "slow down": a spent quota or an
# unpaid account needs the user to act, while a plain rate limit is worth retrying.
_QUOTA_WORDS = ("quota", "billing", "credit", "insufficient_funds", "exceeded your current")


class ProviderAuthError(EngineError):
    """The provider rejected the key (401/403) or the account is out of quota or unpaid.

    Carries the SDK's own message: it names the real problem (wrong key, project without access,
    exhausted quota) better than anything this layer could invent, and the API surfaces it as-is.
    """

    def __init__(self, provider: str, message: str) -> None:
        super().__init__(message)
        self.provider = provider


def mentions_quota(message: str) -> bool:
    lowered = message.lower()
    return any(word in lowered for word in _QUOTA_WORDS)
