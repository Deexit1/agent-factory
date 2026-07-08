from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.auth import SERVICE_ACTOR, ActorContext, get_actor_context
from api.contracts import (
    AddEgressRuleRequest,
    EffectiveEgressDomainsOut,
    EgressRuleListOut,
    EgressRuleOut,
)
from api.db.session import get_db
from api.repositories import egress_repository

router = APIRouter(
    prefix="/orgs/{org_id}/egress-rules", tags=["egress"], dependencies=[Depends(get_actor_context)]
)

# Service-token-only, mirrors provider_keys.py's runtime_router split — the
# orchestrator fetches the merged base+org allow-list at sandbox-provision time.
effective_router = APIRouter(
    prefix="/orgs/{org_id}/egress-rules", tags=["egress"], dependencies=[Depends(get_actor_context)]
)


def _require_member(org_id: str, actor_context: ActorContext) -> None:
    # Cross-tenant reads 404, not 403 (T-201 AC1 convention).
    if actor_context.org_id != org_id:
        raise HTTPException(status_code=404, detail="org not found")


def _require_staff(actor_context: ActorContext) -> None:
    # SPEC-204 AC3: "org-specific egress addition works only after staff approval" —
    # reuses the exact ActorContext.is_platform_staff gate routers/admin.py already
    # established for T-201 impersonation, no new auth concept.
    if not actor_context.is_platform_staff:
        raise HTTPException(status_code=403, detail="platform staff only")


def _staff_email(actor_context: ActorContext) -> str:
    return actor_context.actor.removeprefix("human:").removeprefix("staff:")


@router.get("", response_model=EgressRuleListOut)
def list_rules(
    org_id: str,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> EgressRuleListOut:
    _require_member(org_id, actor_context)
    rules = egress_repository.list_rules(db, org_id=org_id)
    return EgressRuleListOut(items=[EgressRuleOut.model_validate(r) for r in rules])


@router.post("", response_model=EgressRuleOut, status_code=201)
def add_rule(
    org_id: str,
    request: AddEgressRuleRequest,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> EgressRuleOut:
    _require_member(org_id, actor_context)
    _require_staff(actor_context)
    rule = egress_repository.add_rule(
        db, org_id=org_id, domain=request.domain, approved_by=_staff_email(actor_context)
    )
    db.commit()
    return EgressRuleOut.model_validate(rule)


@router.delete("/{rule_id}", status_code=204)
def remove_rule(
    org_id: str,
    rule_id: int,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> None:
    _require_member(org_id, actor_context)
    _require_staff(actor_context)
    removed = egress_repository.remove_rule(db, rule_id, org_id=org_id)
    if not removed:
        raise HTTPException(status_code=404, detail="egress rule not found")
    db.commit()


@effective_router.get("/effective", response_model=EffectiveEgressDomainsOut)
def get_effective_domains(
    org_id: str,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> EffectiveEgressDomainsOut:
    if actor_context.actor != SERVICE_ACTOR:
        raise HTTPException(
            status_code=403, detail="effective egress resolution is service-principal only"
        )
    domains = egress_repository.list_effective_domains(db, org_id=org_id)
    return EffectiveEgressDomainsOut(domains=domains)
