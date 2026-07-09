"""T-206 (SPEC-206 AC2): screen_content is a pure function — zero I/O, zero LLM call.
Hard-reject fixtures cover the four named categories (malware, credential attacks,
scraping farms, spam infra); borderline fixtures cover terms that are prohibited-use-
adjacent but have legitimate uses, so they route to staff review instead of an
automatic reject. This is the mechanism AC2 is actually verified against, since no
live Anthropic credit exists in this environment for the optional LLM layer."""

from api.services.intake_screening_service import screen_content


def test_clean_idea_passes() -> None:
    verdict = screen_content(
        "Build a customer support ticketing dashboard",
        {"description": "Track and triage support tickets for our SaaS product."},
    )
    assert verdict.decision == "pass"
    assert verdict.reason is None


def test_hard_reject_malware_in_title() -> None:
    verdict = screen_content("Build a keylogger for Windows", None)
    assert verdict.decision == "reject"
    assert verdict.matched_rule == "malware"
    assert "keylogger" in (verdict.reason or "")


def test_hard_reject_credential_attack_in_spec() -> None:
    verdict = screen_content(
        "Automation tool",
        {"description": "A tool that performs credential stuffing against login forms."},
    )
    assert verdict.decision == "reject"
    assert verdict.matched_rule == "credential_attack"


def test_hard_reject_scraping_farm() -> None:
    verdict = screen_content("Set up a scraping farm for e-commerce prices", None)
    assert verdict.decision == "reject"
    assert verdict.matched_rule == "scraping_farm"


def test_hard_reject_spam_infra() -> None:
    verdict = screen_content(
        "Marketing tool", {"description": "Send an email spam campaign to purchased lists."}
    )
    assert verdict.decision == "reject"
    assert verdict.matched_rule == "spam_infra"


def test_borderline_scraper_routes_to_review_not_reject() -> None:
    verdict = screen_content(
        "Build a web scraper", {"description": "Scrape our own product catalog nightly."}
    )
    assert verdict.decision == "review"
    assert verdict.matched_rule == "scraping_adjacent"


def test_borderline_penetration_testing_routes_to_review() -> None:
    verdict = screen_content(
        "Security audit tool", {"description": "Automated penetration testing for our own app."}
    )
    assert verdict.decision == "review"
    assert verdict.matched_rule == "security_adjacent"


def test_hard_reject_takes_priority_over_borderline_match_in_same_content() -> None:
    """A title matching both a hard-reject and a borderline pattern must reject, not
    merely queue for review — hard-reject rules are checked first."""
    verdict = screen_content("Web scraper for a credential stuffing campaign", None)
    assert verdict.decision == "reject"
    assert verdict.matched_rule == "credential_attack"


def test_case_insensitive_matching() -> None:
    verdict = screen_content("BUILD A KEYLOGGER", None)
    assert verdict.decision == "reject"
