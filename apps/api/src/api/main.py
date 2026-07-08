import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from api.routers import (
    admin,
    agent_runs,
    auth,
    capability_registry,
    dashboard,
    health,
    merge_queue,
    orgs,
    tickets,
    webhooks,
    ws_tickets,
)
from api.ws.broadcaster import broadcaster


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    broadcaster.bind_loop(asyncio.get_running_loop())
    yield


app = FastAPI(title="Agent Factory API", lifespan=lifespan)

# Dev-only: the web app's Vite dev server runs on a different origin. SPEC-006 will
# replace this with a proper allow-list once real deployments/SSO exist.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Only used to hold Authlib's transient OAuth state/nonce during the /auth/login ->
# /auth/callback round-trip - not our own session token, which is a stateless JWT.
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_JWT_SECRET") or "insecure-dev-only-session-secret",
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(tickets.router)
app.include_router(agent_runs.router)
app.include_router(webhooks.router)
app.include_router(dashboard.router)
app.include_router(ws_tickets.router)
app.include_router(capability_registry.router)
app.include_router(merge_queue.router)
app.include_router(orgs.router)
app.include_router(admin.router)
