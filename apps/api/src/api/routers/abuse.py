"""T-206 (SPEC-206 AC5): org strikes + appeal. Imposing a strike and resolving an
appeal are both platform-staff-only (`/admin/...`, mirrors `routers/admin.py`'s
impersonation gate); requesting an appeal is owner-initiated self-service (`/orgs/{id}/
strikes/...`, mirrors `orgs.py`'s owner-only invite gate).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.auth import ActorContext, get_actor_context
from api.contracts import (
    AppealStrikeRequest,
    OrgStrikeListOut,
    OrgStrikeOut,
    ResolveAppealRequest,
    StrikeOrgRequest,
)
from api.db.session import get_db
from api.services import abuse_service

router = APIRouter(
    prefix="/orgs/{org_id}/strikes", tags=["abuse"], dependencies=[Depends(get_actor_context)]
)
admin_router = APIRouter(prefix="/admin", tags=["abuse"], dependencies=[Depends(get_actor_context)])


def _require_member(org_id: str, actor_context: ActorContext) -> None:
    if actor_context.org_id != org_id:
        raise HTTPException(status_code=404, detail="org not found")


def _require_member_or_staff(org_id: str, actor_context: ActorContext) -> None:
    # Platform staff can already see everything about any org via impersonation
    # (T-201) — this lets the staff-facing strikes admin page read an org's strikes
    # directly, without a separate "view as org" round trip first.
    if actor_context.org_id != org_id and not actor_context.is_platform_staff:
        raise HTTPException(status_code=404, detail="org not found")


def _require_owner(actor_context: ActorContext) -> None:
    if actor_context.role != "owner":
        raise HTTPException(status_code=403, detail="only the org owner may appeal a strike")


def _require_staff(actor_context: ActorContext) -> None:
    if not actor_context.is_platform_staff:
        raise HTTPException(status_code=403, detail="platform staff only")


@router.get("", response_model=OrgStrikeListOut)
def list_my_strikes(
    org_id: str,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> OrgStrikeListOut:
    _require_member_or_staff(org_id, actor_context)
    strikes = abuse_service.list_strikes(db, org_id=org_id)
    return OrgStrikeListOut(items=[OrgStrikeOut.model_validate(s) for s in strikes])


@router.post("/{strike_id}/appeal", response_model=OrgStrikeOut)
def appeal_strike(
    org_id: str,
    strike_id: int,
    request: AppealStrikeRequest,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> OrgStrikeOut:
    _require_member(org_id, actor_context)
    _require_owner(actor_context)
    try:
        strike = abuse_service.request_appeal(
            db, strike_id, org_id=org_id, note=request.note, actor=actor_context.actor
        )
    except abuse_service.StrikeNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except abuse_service.StrikeNotActive as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return OrgStrikeOut.model_validate(strike)


@admin_router.post("/orgs/{org_id}/strikes", response_model=OrgStrikeOut, status_code=201)
def strike_org(
    org_id: str,
    request: StrikeOrgRequest,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> OrgStrikeOut:
    _require_staff(actor_context)
    try:
        strike, _blocked = abuse_service.strike_org(
            db, org_id=org_id, reason=request.reason, actor=actor_context.actor
        )
    except abuse_service.OrgNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return OrgStrikeOut.model_validate(strike)


@admin_router.post("/strikes/{strike_id}/resolve-appeal", response_model=OrgStrikeOut)
def resolve_appeal(
    strike_id: int,
    request: ResolveAppealRequest,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> OrgStrikeOut:
    _require_staff(actor_context)
    try:
        strike, _reactivated = abuse_service.resolve_appeal(
            db, strike_id, decision=request.decision, actor=actor_context.actor
        )
    except abuse_service.StrikeNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except abuse_service.StrikeNotAppealed as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return OrgStrikeOut.model_validate(strike)
