"""Jobsy Search Service -- Elasticsearch-powered full-text search."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from shared.middleware import setup_middleware

from app.consumer import start_consumers
from app.elasticsearch_client import close_client, ensure_indices
from app.routes import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_indices()
    consumer_task = asyncio.create_task(start_consumers())
    yield
    consumer_task.cancel()
    await close_client()


app = FastAPI(title="Jobsy Search", version="0.1.0", lifespan=lifespan)
setup_middleware(app)
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "search"}
