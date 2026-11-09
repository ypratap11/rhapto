"""Fixed sentences shown to people whose provider key was refused.

Shared by the worker (which stores them on the task row) and the admin classifier, so the two can
never drift apart. Moved byte for byte out of `worker/tasks.py`.
"""

from __future__ import annotations

# Shown instead of the provider's own words when the rejected key belongs to the deployment rather
# than to the person reading it. Names no provider, no model, no account and no balance.
SHARED_KEY_REJECTED_MESSAGE = (
    "This instance's shared LLM key was refused by its provider. Add your own key in Settings to "
    "keep going, or ask whoever runs this instance to check it."
)


# Display names for the user-key sentences. Written out (not the registry label, which says
# "Groq (free tier)") because these two sentences are matched word for word by the web
# (`SETTINGS_SENTENCES` in apps/web/src/lib/coach/errors.ts). Change one side, change the other.
PROVIDER_DISPLAY_NAMES = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "gemini": "Google Gemini",
    "groq": "Groq",
    "openrouter": "OpenRouter",
}


def user_key_message(kind: str, provider_id: str) -> str | None:
    """What a person whose OWN key was refused should read, or None for a provider we have no name for."""
    name = PROVIDER_DISPLAY_NAMES.get(provider_id)
    if name is None:
        return None
    if kind == "quota":
        return f"Your {name} account is out of credit. Add credit with {name} or paste a different key in Settings."
    return (
        f"Your {name} key was refused. It may have expired or been revoked. "
        "Paste a new key in Settings, then try again."
    )
