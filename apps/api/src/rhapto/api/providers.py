"""The provider registry, shaped for the wire.

Its own module because two places need it and neither should import the other: the Settings router
puts it in every `LlmSettingsOut`, and the error handlers put it in the 409 `llm_key_unreadable`
problem body — the one response the Settings page gets when it cannot get a 200, and therefore the
one place the web app would otherwise have to keep its own copy of this list.
"""

from __future__ import annotations

from rhapto.api.schemas import ProviderInfoOut
from rhapto.engine.providers.registry import PROVIDERS


def provider_list() -> list[ProviderInfoOut]:
    return [
        ProviderInfoOut(id=i.id, label=i.label, models=list(i.models), default=i.default)
        for i in PROVIDERS.values()
    ]
