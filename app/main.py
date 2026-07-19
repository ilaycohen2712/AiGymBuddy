import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db.migrate import run_migrations
from app.db.pool import get_pool
from app.whatsapp.webhook import router as webhook_router

# Without this, Python defaults to WARNING — every logger.info() call in the
# app (meal logged, photo not recognized as food, duplicate skipped) would be
# silently invisible in production, leaving only failures ever logged.
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await get_pool()
    await run_migrations(pool)
    yield


app = FastAPI(title="AiGymBuddy", lifespan=lifespan)
app.include_router(webhook_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
