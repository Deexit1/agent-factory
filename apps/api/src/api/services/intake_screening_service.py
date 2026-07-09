"""T-206 (SPEC-206 AC2): a pure, dependency-free two-tier keyword/regex screen for
idea/task content at intake. Zero I/O, zero LLM call — the only thing that needs to be
true for AC2 to be provably green in an environment with zero live Anthropic credit
(see docs/06-tech-stack.md's other disclosed live-infra gaps for the same category of
constraint). An optional LLM-based classifier layer is scaffolded elsewhere
(prompts/intake-screener.md) but feature-flagged off by default and can only ever
tighten a verdict (pass -> review), never weaken this layer's guarantee.
"""

import json
import re
from dataclasses import dataclass
from typing import Literal

Decision = Literal["pass", "review", "reject"]

# Hard-reject: unambiguous prohibited-use signatures (SPEC-206's own four categories:
# malware, credential attacks, scraping farms, spam infra). Matched as whole-word/
# phrase, case-insensitive.
_HARD_REJECT_RULES: tuple[tuple[str, str], ...] = (
    ("malware", r"\bmalware\b"),
    ("malware", r"\bransomware\b"),
    ("malware", r"\bkeylogger\b"),
    ("malware", r"\btrojan\s+horse\b"),
    ("malware", r"\bremote\s+access\s+trojan\b"),
    ("malware", r"\bbotnet\b"),
    ("malware", r"\bworm\s+virus\b"),
    ("credential_attack", r"\bcredential\s+stuffing\b"),
    ("credential_attack", r"\bpassword\s+cracker\b"),
    ("credential_attack", r"\bbrute[\s-]?force\s+login\b"),
    ("credential_attack", r"\bsteal\s+(passwords|credentials)\b"),
    ("credential_attack", r"\bphishing\s+kit\b"),
    ("credential_attack", r"\bcard\s+skimmer\b"),
    ("scraping_farm", r"\bscraping\s+farm\b"),
    ("scraping_farm", r"\bfake\s+account\s+farm\b"),
    ("scraping_farm", r"\bclick\s+farm\b"),
    ("scraping_farm", r"\bbulk\s+scraper\s+farm\b"),
    ("spam_infra", r"\bspam\s+bot\b"),
    ("spam_infra", r"\bspam\s+farm\b"),
    ("spam_infra", r"\bemail\s+spam\s+campaign\b"),
    ("spam_infra", r"\bddos\b"),
    ("spam_infra", r"\bdenial\s+of\s+service\s+attack\b"),
)

# Borderline: adjacent-but-ambiguous terms that a human reviewer should judge — plenty
# of legitimate use cases exist (e.g. "web scraper" for a customer's own data), so these
# route to the staff review queue instead of an automatic reject.
_BORDERLINE_RULES: tuple[tuple[str, str], ...] = (
    ("scraping_adjacent", r"\bweb\s+scraper\b"),
    ("scraping_adjacent", r"\bscraping\s+tool\b"),
    ("automation_adjacent", r"\baccount\s+automation\b"),
    ("automation_adjacent", r"\bproxy\s+rotator\b"),
    ("automation_adjacent", r"\bcaptcha\s+solver\b"),
    ("messaging_adjacent", r"\bbulk\s+(email|messaging)\b"),
    ("messaging_adjacent", r"\bmass\s+email\s+sender\b"),
    ("security_adjacent", r"\bpenetration\s+test(ing)?\b"),
    ("security_adjacent", r"\bvulnerability\s+scanner\b"),
    ("security_adjacent", r"\bbrute[\s-]?force\b"),
)

_HARD_REJECT_COMPILED = [(cat, re.compile(pat, re.IGNORECASE)) for cat, pat in _HARD_REJECT_RULES]
_BORDERLINE_COMPILED = [(cat, re.compile(pat, re.IGNORECASE)) for cat, pat in _BORDERLINE_RULES]


@dataclass(frozen=True)
class ScreeningVerdict:
    decision: Decision
    reason: str | None
    matched_rule: str | None


def _searchable_text(title: str, spec: dict[str, object] | None) -> str:
    parts = [title]
    if spec:
        try:
            parts.append(json.dumps(spec, default=str))
        except (TypeError, ValueError):
            parts.append(str(spec))
    return "\n".join(parts)


def screen_content(title: str, spec: dict[str, object] | None) -> ScreeningVerdict:
    """Pure function: title + spec (the raw idea/task content a user submits) in,
    a verdict out. Hard-reject rules are checked before borderline ones so a title that
    happens to match both categories is rejected, not merely queued."""
    text = _searchable_text(title, spec)

    for category, pattern in _HARD_REJECT_COMPILED:
        match = pattern.search(text)
        if match:
            return ScreeningVerdict(
                decision="reject",
                reason=f"matched prohibited-use signature ({category}): {match.group(0)!r}",
                matched_rule=category,
            )

    for category, pattern in _BORDERLINE_COMPILED:
        match = pattern.search(text)
        if match:
            return ScreeningVerdict(
                decision="review",
                reason=f"matched borderline signature ({category}): {match.group(0)!r}",
                matched_rule=category,
            )

    return ScreeningVerdict(decision="pass", reason=None, matched_rule=None)


__all__ = ["Decision", "ScreeningVerdict", "screen_content"]
