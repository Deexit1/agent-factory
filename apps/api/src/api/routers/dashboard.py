from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from api.auth import ActorContext, get_actor_context
from api.contracts import DashboardMetricsOut, EscapedDefectReportIn, EscapedDefectReportOut
from api.db.session import get_db
from api.services import dashboard_service, ticket_service

router = APIRouter(
    prefix="/dashboard", tags=["dashboard"], dependencies=[Depends(get_actor_context)]
)


@router.get("/metrics", response_model=DashboardMetricsOut)
def get_metrics(db: Session = Depends(get_db)) -> DashboardMetricsOut:
    return dashboard_service.compute_metrics(db)


@router.get("/export.csv")
def export_csv(db: Session = Depends(get_db)) -> PlainTextResponse:
    return PlainTextResponse(
        dashboard_service.export_csv(db),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=pilot-dashboard.csv"},
    )


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
        )
    except ticket_service.TicketNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return EscapedDefectReportOut.model_validate(report)
