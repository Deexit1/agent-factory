"""T-206 (SPEC-206 AC3): the platform's Acceptable Use Policy / Terms of Service.

No real legal text is in scope for this ticket — CURRENT_TOS_VERSION and the policy
text below are explicit placeholders pending a real legal decision, same framing as
`billing_plans.py`'s pricing tiers. Bumping CURRENT_TOS_VERSION is how a real ToS
change would be shipped; every org whose latest `TosAcceptance.tos_version` is older
than this constant is re-prompted (AC3's "re-prompted on ToS change").
"""

CURRENT_TOS_VERSION = "2026-07-01"

ACCEPTABLE_USE_POLICY = """
Agent Factory Acceptable Use Policy (placeholder text, pending real legal review)

By using this platform you agree not to submit ideas or tasks that involve:
  - malware, exploits, or other malicious code
  - credential theft, phishing, or other attacks against third-party accounts
  - unauthorized scraping infrastructure or bulk data harvesting
  - spam, botnets, or other abusive infrastructure

Violations may result in a strike against your organization; struck organizations
have their in-flight work blocked (not deleted) pending appeal review by platform
staff.
""".strip()


def is_current(accepted_version: str | None) -> bool:
    return accepted_version == CURRENT_TOS_VERSION


__all__ = ["CURRENT_TOS_VERSION", "ACCEPTABLE_USE_POLICY", "is_current"]
