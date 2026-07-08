"""T-201 AC5: platform-staff impersonation ("view as org") + per-page audit trail."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.auth import ActorContext, get_actor_context, mint_session_token
from api.contracts import PageViewAuditRequest, SessionOut
from api.db.models import UserRole
from api.db.session import get_db
from api.repositories import org_repository

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(get_actor_context)])


@router.post("/orgs/{org_id}/impersonate", response_model=SessionOut)
def impersonate(
    org_id: str,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> SessionOut:
    if not actor_context.is_platform_staff:
        raise HTTPException(status_code=403, detail="platform staff only")

    org = org_repository.get_org(db, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="org not found")

    staff_email = actor_context.actor.removeprefix("human:")
    # Impersonation is always read-mostly (VIEWER), regardless of the staff member's
    # own role elsewhere — "view as org" is for support/debugging visibility, not for
    # acting as if staff were an owner/approver of an org they don't belong to.
    token = mint_session_token(
        staff_email, org_id=org_id, role=UserRole.VIEWER, is_platform_staff=True, impersonating=True
    )
    org_repository.record_staff_audit(
        db, staff_email=staff_email, org_id=org_id, action="impersonate_start"
    )
    db.commit()

    return SessionOut(
        token=token,
        actor=f"staff:{staff_email}",
        role=UserRole.VIEWER,
        org_id=org_id,
        is_platform_staff=True,
        impersonating=True,
    )


@router.post("/audit/page-view", status_code=201)
def audit_page_view(
    request: PageViewAuditRequest,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    if not actor_context.impersonating:
        raise HTTPException(
            status_code=403, detail="only an impersonation session may post page-view audits"
        )

    staff_email = actor_context.actor.removeprefix("staff:")
    org_repository.record_staff_audit(
        db,
        staff_email=staff_email,
        org_id=actor_context.org_id,
        action="page_view",
        path=request.path,
    )
    db.commit()
    return {"ok": True}
