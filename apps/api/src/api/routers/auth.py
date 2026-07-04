import os
from typing import Any

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from api.auth import ActorContext, get_actor_context, mint_session_token
from api.contracts import DevLoginRequest, SessionOut
from api.db.models import UserRole
from api.db.session import get_db
from api.services import user_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _oidc_client() -> Any:
    """Registered lazily so importing this module never requires live IdP config."""
    issuer = os.environ.get("OIDC_ISSUER_URL")
    client_id = os.environ.get("OIDC_CLIENT_ID")
    client_secret = os.environ.get("OIDC_CLIENT_SECRET")
    if not (issuer and client_id and client_secret):
        raise HTTPException(
            status_code=501,
            detail="OIDC is not configured (OIDC_ISSUER_URL/OIDC_CLIENT_ID/OIDC_CLIENT_SECRET)",
        )

    oauth = OAuth()
    oauth.register(
        name="oidc",
        server_metadata_url=f"{issuer.rstrip('/')}/.well-known/openid-configuration",
        client_id=client_id,
        client_secret=client_secret,
        client_kwargs={"scope": "openid email profile"},
    )
    return oauth.oidc


@router.get("/login")
async def login(request: Request) -> Any:
    client = _oidc_client()
    redirect_uri = os.environ.get("OIDC_REDIRECT_URI", str(request.url_for("callback")))
    return await client.authorize_redirect(request, redirect_uri)


@router.get("/callback", name="callback")
async def callback(request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
    client = _oidc_client()
    token = await client.authorize_access_token(request)
    userinfo = token.get("userinfo")
    if not userinfo or "email" not in userinfo:
        raise HTTPException(status_code=401, detail="OIDC provider did not return an email claim")

    user = user_service.get_or_create_user(db, userinfo["email"])
    session_token = mint_session_token(user.email, user.role)
    success_url = os.environ.get("WEB_LOGIN_SUCCESS_URL", "http://localhost:5173")
    return RedirectResponse(f"{success_url}#token={session_token}")


@router.post("/dev-login", response_model=SessionOut)
def dev_login(request: DevLoginRequest, db: Session = Depends(get_db)) -> SessionOut:
    if os.environ.get("AUTH_DEV_MODE", "").lower() != "true":
        raise HTTPException(status_code=404, detail="not found")

    user = user_service.get_or_create_user(db, request.email, role_override=request.role)
    return SessionOut(
        token=mint_session_token(user.email, user.role),
        actor=f"human:{user.email}",
        role=user.role,
    )


@router.get("/me", response_model=SessionOut)
def me(actor_context: ActorContext = Depends(get_actor_context)) -> SessionOut:
    return SessionOut(token="", actor=actor_context.actor, role=UserRole(actor_context.role))
