from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.auth import ActorContext, get_actor_context
from api.contracts import (
    BillingUsageLineOut,
    BillingUsageOut,
    OrgBillingOut,
    PortalLinkOut,
    SetPlanRequest,
    SubscribeOut,
    SubscribeRequest,
)
from api.db.session import get_db
from api.services import billing_service

router = APIRouter(
    prefix="/orgs/{org_id}/billing", tags=["billing"], dependencies=[Depends(get_actor_context)]
)


def _require_member(org_id: str, actor_context: ActorContext) -> None:
    # Cross-tenant reads 404, not 403 (T-201 AC1 convention).
    if actor_context.org_id != org_id:
        raise HTTPException(status_code=404, detail="org not found")


def _require_owner(actor_context: ActorContext) -> None:
    if actor_context.role != "owner":
        raise HTTPException(status_code=403, detail="only the org owner may change billing")


@router.get("", response_model=OrgBillingOut)
def get_billing(
    org_id: str,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> OrgBillingOut:
    _require_member(org_id, actor_context)
    try:
        org = billing_service.get_org_billing(db, org_id)
    except billing_service.OrgNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return OrgBillingOut(
        org_id=org.id,
        plan=org.plan,
        pending_plan=org.pending_plan,
        pending_plan_effective_at=org.pending_plan_effective_at,
        current_period_end=org.current_period_end,
        billing_status=org.billing_status,
        dunning_grace_until=org.dunning_grace_until,
    )


@router.post("/subscribe", response_model=SubscribeOut, status_code=201)
def subscribe(
    org_id: str,
    request: SubscribeRequest,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> SubscribeOut:
    _require_member(org_id, actor_context)
    _require_owner(actor_context)
    try:
        checkout_url = billing_service.subscribe(
            db, org_id=org_id, plan_key=request.plan, email=request.email
        )
    except billing_service.OrgNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except billing_service.UnknownPlan as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return SubscribeOut(checkout_url=checkout_url)


@router.post("/plan", response_model=OrgBillingOut)
def set_plan(
    org_id: str,
    request: SetPlanRequest,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> OrgBillingOut:
    _require_member(org_id, actor_context)
    _require_owner(actor_context)
    try:
        org = billing_service.set_plan(db, org_id, request.plan)
    except billing_service.OrgNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except billing_service.UnknownPlan as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return OrgBillingOut(
        org_id=org.id,
        plan=org.plan,
        pending_plan=org.pending_plan,
        pending_plan_effective_at=org.pending_plan_effective_at,
        current_period_end=org.current_period_end,
        billing_status=org.billing_status,
        dunning_grace_until=org.dunning_grace_until,
    )


@router.get("/portal-link", response_model=PortalLinkOut)
def portal_link(
    org_id: str,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> PortalLinkOut:
    _require_member(org_id, actor_context)
    try:
        url = billing_service.portal_link(db, org_id=org_id)
    except billing_service.OrgNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except billing_service.BillingServiceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return PortalLinkOut(url=url)


@router.get("/usage", response_model=BillingUsageOut)
def get_usage(
    org_id: str,
    period_start: date | None = Query(default=None),
    period_end: date | None = Query(default=None),
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> BillingUsageOut:
    """AC5: independently computed from usage_events/agent_runs/ticket_events — the
    reconciliation test checks this against billing_usage_reports, what the metering
    job actually recorded as sent to Razorpay for the same period."""
    _require_member(org_id, actor_context)
    if period_end is None:
        period_end = datetime.now(UTC).date()
    if period_start is None:
        period_start = period_end - timedelta(days=30)

    try:
        invoice = billing_service.compute_live_invoice_for_period(
            db, org_id=org_id, start_date=period_start, end_date=period_end
        )
    except billing_service.OrgNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return BillingUsageOut(
        org_id=org_id,
        period_start=period_start,
        period_end=period_end,
        plan_key=invoice.plan_key,
        base_fee_inr=invoice.base_fee_inr,
        total_inr=invoice.total_inr,
        line_items=[
            BillingUsageLineOut(
                kind=item.kind,
                included=item.included,
                used=item.used,
                overage=item.overage,
                rate_inr=item.rate_inr,
                amount_inr=item.amount_inr,
            )
            for item in invoice.line_items
        ],
    )
