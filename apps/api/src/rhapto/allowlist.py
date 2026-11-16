"""Email allowlist matching shared by the API guards and the service layer.

Dependency-free on purpose: `services/` may not import `rhapto.api`.
"""

from __future__ import annotations


def is_allowed_email(email: str, allowed_emails: str, allowed_domains: str) -> bool:
    """Casefolded exact-match or domain-match against the two comma-separated allowlists.

    An empty allowlist fails closed: "unconfigured" must never mean "open", matching the
    codebase's existing posture on an empty `rhapto_api_token`.
    """
    normalized = email.casefold().strip()
    exact = {e.strip().casefold() for e in allowed_emails.split(",") if e.strip()}
    # The emptiness check must run AFTER `lstrip("@")`, not before: a domains entry of exactly "@"
    # is truthy at `d.strip()` and only becomes "" once the leading "@" is stripped. Checking
    # truthiness before the strip (the earlier form of this function) let a bare "@" domain entry
    # normalize to "", which then matched every email with no "@" in it at all -- an auth bypass
    # (verified: `is_allowed_email("attacker", "", "@")` was `True`).
    domains: set[str] = set()
    for d in allowed_domains.split(","):
        stripped = d.strip().casefold().lstrip("@")
        if stripped:
            domains.add(stripped)
    if not exact and not domains:
        return False
    if normalized in exact:
        return True
    # Exactly one "@" required before domain-matching: without this, an email like
    # "a@evil.com@company.io" would `rsplit("@", 1)` to domain "company.io" and be admitted, even
    # though the real domain (by any mail-parsing rule) is "evil.com".
    if normalized.count("@") != 1:
        return False
    local, domain = normalized.split("@", 1)
    # A non-empty local part required too: "@example.com" alone (no IdP issues this, but nothing
    # upstream rules it out either) would otherwise still satisfy `count("@") == 1` and match
    # domain "example.com".
    if not local:
        return False
    return domain in domains
