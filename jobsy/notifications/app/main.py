"""Jobsy Notification Service -- push notifications and notification history."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from shared.database import init_db
from shared.middleware import setup_middleware

from app.consumer import start_consumers
from app.routes import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    consumer_task = asyncio.create_task(start_consumers())
    yield
    consumer_task.cancel()


app = FastAPI(title="Jobsy Notifications", version="0.1.0", lifespan=lifespan)
setup_middleware(app)
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "notifications"}
