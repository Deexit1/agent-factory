from fastapi import FastAPI

from api.routers import health, tickets

app = FastAPI(title="Agent Factory API")
app.include_router(health.router)
app.include_router(tickets.router)
