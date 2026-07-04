from fastapi import FastAPI

from api.routers import health

app = FastAPI(title="Agent Factory API")
app.include_router(health.router)
