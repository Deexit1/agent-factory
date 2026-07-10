"""T-201 AC5: platform-staff impersonation ("view as org") + per-page audit trail.
T-211: cross-org agent-dispatch discovery (service-principal only, see below)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.auth import SERVICE_ACTOR, ActorContext, get_actor_context, mint_session_token
from api.contracts import (
    DispatchableTicketListOut,
    DispatchableTicketOut,
    PageViewAuditRequest,
    SessionOut,
)
from api.db.models import UserRole
from api.db.session import get_db
from api.repositories import org_repository
from api.repositories import ticket_repository as ticket_repo

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


@router.get("/dispatch/ready-tickets", response_model=DispatchableTicketListOut)
def list_dispatchable_tickets(
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> DispatchableTicketListOut:
    """T-211: cross-org, deliberately not filtered by actor_context.org_id — the one
    thing the orchestrator's dispatcher needs that no org-scoped endpoint can give it:
    which (ticket_id, org_id) pairs need an agent run, across every org at once.
    Gated the same way GET /orgs/{org_id}/llm/runtime-keys already is (actor ==
    SERVICE_ACTOR), not is_platform_staff — a human staff session, even impersonating,
    still only ever sees one org at a time by design."""
    if actor_context.actor != SERVICE_ACTOR:
        raise HTTPException(status_code=403, detail="dispatch discovery is service-principal only")
    tickets = ticket_repo.list_dispatchable_tickets(db)
    return DispatchableTicketListOut(
        items=[DispatchableTicketOut.model_validate(t) for t in tickets]
    )
