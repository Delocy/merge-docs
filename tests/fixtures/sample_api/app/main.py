from fastapi import FastAPI

from app.routers import orders, health

app = FastAPI()
app.include_router(orders.router, prefix="/v1")
app.include_router(health.router)
