import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import health, tickets, ws_tickets
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

app.include_router(health.router)
app.include_router(tickets.router)
app.include_router(ws_tickets.router)
