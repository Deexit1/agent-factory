from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from api.contracts import CIResultWebhook, TicketOut
from api.db.session import get_db
from api.services import ticket_service, webhook_service

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/ci-result", response_model=TicketOut)
async def ci_result(request: Request, db: Session = Depends(get_db)) -> TicketOut:
    raw_body = await request.body()
    if not webhook_service.verify_signature(raw_body, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(status_code=401, detail="invalid webhook signature")

    payload = CIResultWebhook.model_validate_json(raw_body)

    try:
        ticket = webhook_service.handle_ci_result(
            db,
            payload.ticket_id,
            conclusion=payload.conclusion,
            suite=payload.suite,
            raw_log=payload.raw_log,
        )
    except ticket_service.TicketNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except webhook_service.TicketNotInQA as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ticket_service.TransitionRefused as exc:
        raise HTTPException(status_code=409, detail=exc.reason) from exc

    return TicketOut.model_validate(ticket)
