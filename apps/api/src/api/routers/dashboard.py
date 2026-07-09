from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from api.auth import ActorContext, get_actor_context
from api.contracts import (
    DashboardMetricsOut,
    EscapedDefectReportIn,
    EscapedDefectReportOut,
    FunnelCohortOut,
    FunnelStageCountOut,
    SpendBreakdownOut,
)
from api.db.session import get_db
from api.services import dashboard_service, onboarding_service, ticket_service

router = APIRouter(
    prefix="/dashboard", tags=["dashboard"], dependencies=[Depends(get_actor_context)]
)


@router.get("/metrics", response_model=DashboardMetricsOut)
def get_metrics(
    actor_context: ActorContext = Depends(get_actor_context), db: Session = Depends(get_db)
) -> DashboardMetricsOut:
    return dashboard_service.compute_metrics(db, org_id=actor_context.org_id)


@router.get("/export.csv")
def export_csv(
    actor_context: ActorContext = Depends(get_actor_context), db: Session = Depends(get_db)
) -> PlainTextResponse:
    return PlainTextResponse(
        dashboard_service.export_csv(db, org_id=actor_context.org_id),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=pilot-dashboard.csv"},
    )


@router.get("/spend-by-profile", response_model=SpendBreakdownOut)
def get_spend_by_profile(
    actor_context: ActorContext = Depends(get_actor_context), db: Session = Depends(get_db)
) -> SpendBreakdownOut:
    return dashboard_service.spend_by_profile(db, org_id=actor_context.org_id)


@router.get("/spend-by-prompt-version", response_model=SpendBreakdownOut)
def get_spend_by_prompt_version(
    actor_context: ActorContext = Depends(get_actor_context), db: Session = Depends(get_db)
) -> SpendBreakdownOut:
    return dashboard_service.spend_by_prompt_version(db, org_id=actor_context.org_id)


@router.post("/escaped-defects", response_model=EscapedDefectReportOut, status_code=201)
def report_escaped_defect(
    request: EscapedDefectReportIn,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> EscapedDefectReportOut:
    try:
        report = dashboard_service.record_escaped_defect(
            db,
            ticket_id=request.ticket_id,
            note=request.note,
            reported_by=actor_context.actor,
            org_id=actor_context.org_id,
        )
    except ticket_service.TicketNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return EscapedDefectReportOut.model_validate(report)


@router.get("/funnel", response_model=FunnelCohortOut)
def get_funnel(
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> FunnelCohortOut:
    """T-206 (SPEC-206 AC4): a platform-wide cohort report, not this caller's own org's
    data — staff-only, deliberately not gated by actor_context.org_id equality."""
    if not actor_context.is_platform_staff:
        raise HTTPException(status_code=403, detail="platform staff only")
    if end is None:
        end = datetime.now(UTC)
    if start is None:
        start = end - timedelta(days=30)

    stages = onboarding_service.compute_funnel_cohort(db, cohort_start=start, cohort_end=end)
    return FunnelCohortOut(
        cohort_start=start,
        cohort_end=end,
        stages=[FunnelStageCountOut(stage=stage, org_count=count) for stage, count in stages],
    )
