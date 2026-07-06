from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.auth import ActorContext, get_actor_context
from api.capability_registry import load_registry
from api.contracts import ProfileUtilisationOut, UtilisationOut
from api.db.session import get_db
from api.repositories import ticket_repository as repo

router = APIRouter(
    prefix="/capability-registry",
    tags=["capability-registry"],
    dependencies=[Depends(get_actor_context)],
)


@router.get("/utilisation", response_model=UtilisationOut)
def get_utilisation(
    actor_context: ActorContext = Depends(get_actor_context), db: Session = Depends(get_db)
) -> UtilisationOut:
    registry = load_registry()
    items = [
        ProfileUtilisationOut(
            profile=profile.id,
            in_progress_count=repo.count_in_progress_by_assignee(
                db, org_id=actor_context.org_id, assignee_agent=profile.id
            ),
            max_parallel=profile.max_parallel,
        )
        for profile in registry.profiles.values()
    ]
    return UtilisationOut(items=items)
