from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.auth import ActorContext, get_actor_context
from api.contracts import EvalFloorOut, OptInEvalFloorRequest
from api.db.session import get_db
from api.services import eval_floors_service

router = APIRouter(
    prefix="/orgs/{org_id}/eval-floors",
    tags=["eval-floors"],
    dependencies=[Depends(get_actor_context)],
)


def _actor_email(actor_context: ActorContext) -> str:
    return actor_context.actor.removeprefix("human:").removeprefix("staff:")


@router.get("", response_model=EvalFloorOut)
def get_eval_floor(
    org_id: str,
    agent_role: str,
    provider: str,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> EvalFloorOut:
    if actor_context.org_id != org_id:
        raise HTTPException(status_code=404, detail="org not found")
    return eval_floors_service.get_eval_floor(
        db, org_id=org_id, agent_role=agent_role, provider=provider
    )


@router.post("/opt-in", response_model=EvalFloorOut, status_code=201)
def opt_in_eval_floor(
    org_id: str,
    request: OptInEvalFloorRequest,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> EvalFloorOut:
    if actor_context.org_id != org_id:
        raise HTTPException(status_code=404, detail="org not found")
    if actor_context.role != "owner":
        raise HTTPException(
            status_code=403, detail="only the org owner may opt into an unverified provider"
        )
    eval_floors_service.opt_in(
        db,
        org_id=org_id,
        agent_role=request.agent_role,
        provider=request.provider,
        actor_email=_actor_email(actor_context),
    )
    return eval_floors_service.get_eval_floor(
        db, org_id=org_id, agent_role=request.agent_role, provider=request.provider
    )
