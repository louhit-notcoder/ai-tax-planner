from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api import (
    assistant_routes,
    auth_routes,
    case_routes,
    computation_routes,
    document_routes,
    export_routes,
    fact_routes,
    legal_routes,
    privacy_routes,
    review_routes,
    tenant_routes,
)
from .config import get_settings
from .database import create_all
from .rate_limit import RateLimiter
from .logging_utils import configure_logging

configure_logging()
settings = get_settings()
rate_limiter = RateLimiter()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.is_production:
        create_all()
    yield
    await rate_limiter.close()


app = FastAPI(
    title="Green Papaya AI Tax Assistant",
    version="3.0.0",
    description="Evidence-linked, deterministic Indian tax preparation and review workspace.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
)


@app.middleware("http")
async def security_and_rate_limit(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    # Only apply origin check for non-API routes (allow all API origins for file uploads)
    # The CORSMiddleware handles API CORS properly
    if not request.url.path.startswith("/api/") and request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        if origin and origin not in settings.cors_origins:
            return JSONResponse(status_code=403, content={"detail": f"Origin '{origin}' is not allowed. Allowed: {list(settings.cors_origins)}", "request_id": request_id}, headers={"X-Request-ID": request_id})
    client = request.client.host if request.client else "unknown"
    limit = 300 if request.url.path.startswith("/api/health") else 120
    if not await rate_limiter.allowed(client, limit=limit):
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded", "request_id": request_id},
            headers={"X-Request-ID": request_id, "Retry-After": "60"},
        )
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'"
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "no-cache"
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
    return response


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "version": "3.0.0",
        "environment": settings.environment,
        "tax_scope": "AY 2026-27 code-complete pending CA certification",
    }


for router in [
    auth_routes.router,
    tenant_routes.router,
    case_routes.router,
    document_routes.router,
    fact_routes.router,
    computation_routes.router,
    assistant_routes.router,
    export_routes.router,
    legal_routes.router,
    privacy_routes.router,
    review_routes.router,
]:
    app.include_router(router, prefix="/api")
