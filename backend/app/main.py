"""ASEELO Video API - FastAPI application entrypoint."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.errors import register_exception_handlers
from app.logging_config import configure_logging, get_logger, request_id_var
from app.rate_limit import limiter
from app.routers import auth, brand, jobs, templates, videos

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info("aseelo_api_started", extra={"app_env": settings.app_env})
    yield


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=_lifespan)

app.state.limiter = limiter
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Without this the browser hides these from cross-origin JS, so a download
    # cannot read the server-supplied filename and clients cannot log request IDs.
    expose_headers=["Content-Disposition", "X-Request-ID"],
)

register_exception_handlers(app)


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(_: Request, __: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"error": {"code": "rate_limited", "message": "Too many requests. Please slow down."}},
    )


@app.middleware("http")
async def _request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    request_id_var.set(request_id)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


if settings.storage_provider == "local":
    Path(settings.storage_path).mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=settings.storage_path), name="media")

app.include_router(auth.router)
app.include_router(brand.router)
app.include_router(templates.router)
app.include_router(videos.router)
app.include_router(jobs.router)
app.include_router(jobs.dashboard_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
