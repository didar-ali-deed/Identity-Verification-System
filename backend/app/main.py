import logging
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.idv import router as idv_router
from app.config import get_settings
from app.middleware.cors import setup_cors
from app.middleware.rate_limit import setup_rate_limiter
from app.middleware.security import setup_security

settings = get_settings()


def setup_logging() -> None:
    log_level = logging.DEBUG if settings.debug else logging.INFO
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer() if settings.is_production else structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger = structlog.get_logger()
    await logger.ainfo("Starting Identity Verification System", environment=settings.environment)
    yield
    await logger.ainfo("Shutting down Identity Verification System")


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Production-grade Identity Verification System API",
    docs_url="/api/docs" if not settings.is_production else None,
    redoc_url="/api/redoc" if not settings.is_production else None,
    openapi_url="/api/openapi.json" if not settings.is_production else None,
    lifespan=lifespan,
)

setup_cors(app)
setup_rate_limiter(app)
setup_security(app)

# Routers
app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(idv_router, prefix=settings.api_v1_prefix)
app.include_router(admin_router, prefix=settings.api_v1_prefix)


@app.get("/api/v1/health", tags=["Health"])
async def health_check() -> dict:
    health = {
        "status": "healthy",
        "version": "1.0.0",
        "environment": settings.environment,
        "checks": {},
    }

    # Check database connectivity
    try:
        from sqlalchemy import text

        from app.database import engine

        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        health["checks"]["database"] = "connected"
    except Exception:
        health["checks"]["database"] = "unavailable"
        health["status"] = "degraded"

    # Check Redis connectivity
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.redis_url)
        await r.ping()
        await r.aclose()
        health["checks"]["redis"] = "connected"
    except Exception:
        health["checks"]["redis"] = "unavailable"
        health["status"] = "degraded"

    return health


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger = structlog.get_logger()
    await logger.aerror(
        "Unhandled exception",
        path=str(request.url),
        method=request.method,
        error=str(exc),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
