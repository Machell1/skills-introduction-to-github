"""Jobsy Admin Service -- dashboard, moderation, user management, audit logging."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from shared.database import init_db
from shared.middleware import setup_middleware

from app.routes import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Jobsy Admin", version="0.1.0", lifespan=lifespan)
setup_middleware(app)
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "admin"}
