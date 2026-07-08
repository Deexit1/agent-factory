import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from api.contracts import CIResultWebhook, TicketOut
from api.db.session import get_db
from api.services import github_webhook_service, ticket_service, webhook_service

logger = logging.getLogger(__name__)

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


@router.post("/github")
async def github_webhook(request: Request, db: Session = Depends(get_db)) -> dict[str, str]:
    """T-203 (SPEC-203 AC3/AC4): GitHub's native App webhook delivery — signature
    verified against GITHUB_APP_WEBHOOK_SECRET, distinct from the CI-result route
    above (fired by this repo's own agent-pr-gate workflow, not by GitHub itself)."""
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    if not github_webhook_service.verify_signature(raw_body, signature):
        logger.warning("rejected GitHub webhook delivery: invalid signature")
        raise HTTPException(status_code=401, detail="invalid webhook signature")

    event = request.headers.get("X-GitHub-Event", "")
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="invalid JSON body") from exc

    if event == "installation" and payload.get("action") == "deleted":
        installation = payload.get("installation") or {}
        installation_id = installation.get("id")
        if isinstance(installation_id, int):
            github_webhook_service.handle_installation_deleted(
                db, installation_id=installation_id
            )
    elif event == "check_run" and payload.get("action") == "completed":
        installation = payload.get("installation") or {}
        repository = payload.get("repository") or {}
        check_run = payload.get("check_run") or {}
        check_suite = check_run.get("check_suite") or {}
        installation_id = installation.get("id")
        repo_full_name = repository.get("full_name")
        head_branch = check_suite.get("head_branch")
        conclusion = check_run.get("conclusion")
        if (
            isinstance(installation_id, int)
            and isinstance(repo_full_name, str)
            and isinstance(head_branch, str)
            and isinstance(conclusion, str)
        ):
            github_webhook_service.handle_check_run_completed(
                db,
                installation_id=installation_id,
                repo_full_name=repo_full_name,
                head_branch=head_branch,
                conclusion=conclusion,
            )

    return {"status": "ok"}
