from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db.models import OrgEgressRule

# Mirrors apps/sandbox/src/sandbox/config.py's DEFAULT_ALLOWED_DOMAINS exactly.
# Duplicated rather than imported: apps/api has no dependency on apps/sandbox today
# (and shouldn't grow one just for this small, stable list) — if it drifts, that's an
# easy sync fix, not a design flaw worth a new cross-package coupling.
_BASE_ALLOWED_DOMAINS: list[str] = [
    "pypi.org",
    "files.pythonhosted.org",
    "registry.npmjs.org",
    "github.com",
    "codeload.github.com",
    "api.github.com",
    "api.anthropic.com",
]


def list_rules(session: Session, *, org_id: str) -> list[OrgEgressRule]:
    return list(
        session.execute(
            select(OrgEgressRule).where(OrgEgressRule.org_id == org_id).order_by(OrgEgressRule.id)
        )
        .scalars()
        .all()
    )


def list_effective_domains(session: Session, *, org_id: str) -> list[str]:
    """T-204: the base allow-list every org gets, plus this org's staff-approved
    additions — what `apps/orchestrator` fetches at sandbox-provision time."""
    org_domains = [rule.domain for rule in list_rules(session, org_id=org_id)]
    return list(dict.fromkeys([*_BASE_ALLOWED_DOMAINS, *org_domains]))


def add_rule(
    session: Session, *, org_id: str, domain: str, approved_by: str
) -> OrgEgressRule:
    rule = OrgEgressRule(
        org_id=org_id,
        domain=domain,
        approved_by=approved_by,
        approved_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    session.add(rule)
    session.flush()
    return rule


def remove_rule(session: Session, rule_id: int, *, org_id: str) -> bool:
    rule = session.execute(
        select(OrgEgressRule).where(OrgEgressRule.id == rule_id, OrgEgressRule.org_id == org_id)
    ).scalar_one_or_none()
    if rule is None:
        return False
    session.delete(rule)
    session.flush()
    return True
