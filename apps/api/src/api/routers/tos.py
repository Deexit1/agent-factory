"""T-206 (SPEC-206 AC3): exposes the current ToS version + placeholder policy text so
the org-creation wizard never hardcodes a version that could drift from
api.tos.CURRENT_TOS_VERSION (the value POST /orgs actually validates against)."""

from fastapi import APIRouter, Depends

from api.auth import get_actor_context
from api.contracts import TosOut
from api.tos import ACCEPTABLE_USE_POLICY, CURRENT_TOS_VERSION

router = APIRouter(prefix="/tos", tags=["tos"], dependencies=[Depends(get_actor_context)])


@router.get("", response_model=TosOut)
def get_current_tos() -> TosOut:
    return TosOut(version=CURRENT_TOS_VERSION, policy_text=ACCEPTABLE_USE_POLICY)
