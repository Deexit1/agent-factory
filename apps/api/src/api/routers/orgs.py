from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api import tos
from api.auth import ActorContext, get_actor_context
from api.contracts import (
    AcceptTosRequest,
    CreateOrgRequest,
    InviteMemberRequest,
    OnboardingStatusOut,
    OrgInviteOut,
    OrgListOut,
    OrgMemberListOut,
    OrgMemberOut,
    OrgOut,
)
from api.db.session import get_db
from api.services import onboarding_service, org_service

router = APIRouter(prefix="/orgs", tags=["orgs"], dependencies=[Depends(get_actor_context)])


def _actor_email(actor_context: ActorContext) -> str:
    return actor_context.actor.removeprefix("human:").removeprefix("staff:")


@router.post("/invites/{token}/accept", response_model=OrgMemberOut, status_code=201)
def accept_invite(
    token: str,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> OrgMemberOut:
    """Registered before /{org_id} routes so "invites" is never matched as an org_id."""
    try:
        member = org_service.accept_invite(
            db, token=token, accepting_email=_actor_email(actor_context)
        )
    except org_service.InviteNotFound as exc:
        raise HTTPException(status_code=404, detail="invite not found") from exc

    return OrgMemberOut.model_validate(member)


@router.post("", response_model=OrgOut, status_code=201)
def create_org(
    request: CreateOrgRequest,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> OrgOut:
    if request.tos_version != tos.CURRENT_TOS_VERSION:
        raise HTTPException(
            status_code=422,
            detail=f"tos_version must be the current version ({tos.CURRENT_TOS_VERSION})",
        )
    org = org_service.create_org(
        db,
        name=request.name,
        owner_email=_actor_email(actor_context),
        tos_version=request.tos_version,
    )
    return OrgOut.model_validate(org)


@router.get("/mine", response_model=OrgListOut)
def list_my_orgs(
    actor_context: ActorContext = Depends(get_actor_context), db: Session = Depends(get_db)
) -> OrgListOut:
    orgs = org_service.list_orgs_for_user(db, user_email=_actor_email(actor_context))
    return OrgListOut(items=[OrgOut.model_validate(o) for o in orgs])


@router.post("/{org_id}/invites", response_model=OrgInviteOut, status_code=201)
def invite_member(
    org_id: str,
    request: InviteMemberRequest,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> OrgInviteOut:
    if actor_context.org_id != org_id:
        raise HTTPException(status_code=404, detail="org not found")
    if actor_context.role != "owner":
        raise HTTPException(status_code=403, detail="only the org owner may invite members")

    invite = org_service.invite_member(
        db,
        org_id=org_id,
        email=request.email,
        role=request.role,
        invited_by=actor_context.actor,
    )
    return OrgInviteOut.model_validate(invite)


@router.get("/{org_id}/members", response_model=OrgMemberListOut)
def list_members(
    org_id: str,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> OrgMemberListOut:
    # Cross-tenant reads 404, not 403 (T-201 AC1 convention — matches every other
    # tenant-scoped read in this app: a resource outside your org doesn't exist to you).
    if actor_context.org_id != org_id:
        raise HTTPException(status_code=404, detail="org not found")

    members = org_service.list_members(db, org_id=org_id)
    return OrgMemberListOut(items=[OrgMemberOut.model_validate(m) for m in members])


@router.post("/{org_id}/tos/accept", status_code=204)
def accept_tos(
    org_id: str,
    request: AcceptTosRequest,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> None:
    if actor_context.org_id != org_id:
        raise HTTPException(status_code=404, detail="org not found")
    if actor_context.role not in ("owner", "approver"):
        raise HTTPException(status_code=403, detail="only an approver or owner may accept the ToS")
    if request.tos_version != tos.CURRENT_TOS_VERSION:
        raise HTTPException(
            status_code=422,
            detail=f"tos_version must be the current version ({tos.CURRENT_TOS_VERSION})",
        )
    org_service.accept_tos(
        db,
        org_id=org_id,
        accepted_by=_actor_email(actor_context),
        tos_version=request.tos_version,
    )


@router.get("/{org_id}/onboarding-status", response_model=OnboardingStatusOut)
def get_onboarding_status(
    org_id: str,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> OnboardingStatusOut:
    if actor_context.org_id != org_id:
        raise HTTPException(status_code=404, detail="org not found")
    status = onboarding_service.get_onboarding_status(db, org_id=org_id)
    return OnboardingStatusOut(org_id=org_id, **status)
