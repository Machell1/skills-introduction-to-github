"""Jobsy Chat Service -- real-time messaging for matched users."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from shared.database import init_db
from shared.middleware import setup_middleware

from app.consumer import start_consumer
from app.routes import router
from app.websocket import chat_websocket

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    consumer_task = asyncio.create_task(start_consumer())
    yield
    consumer_task.cancel()


app = FastAPI(title="Jobsy Chat", version="0.1.0", lifespan=lifespan)
setup_middleware(app)
app.include_router(router)


@app.websocket("/ws/{conversation_id}")
async def websocket_endpoint(websocket, conversation_id: str):
    await chat_websocket(websocket, conversation_id)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "chat"}
