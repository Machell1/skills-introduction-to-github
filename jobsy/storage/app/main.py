"""Jobsy Storage Service -- S3-compatible file storage with thumbnailing."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from shared.middleware import setup_middleware

from app.routes import router
from app.s3 import ensure_bucket

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        ensure_bucket()
    except Exception:
        logging.warning("Could not ensure S3 bucket exists -- will retry on first upload")
    yield


app = FastAPI(title="Jobsy Storage", version="0.1.0", lifespan=lifespan)
setup_middleware(app)
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "storage"}
