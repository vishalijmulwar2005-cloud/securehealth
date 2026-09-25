"""SecureHealth care-platform API assembly (TRD v4.1 §2 canonical path).

Production guards (zero-tolerance): production refuses SQLite/in-memory
databases, default JWT secrets, and disabled security scanning.
"""
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .api.v1 import admin, ai, auth, consents, federated, ledger, misc, records, regulator
from .core.config import settings
from .core.errors import register_error_handlers
from .core.rate_limit import limiter, rate_limited_response
from .db.base import Base
from .db.session import SessionLocal, engine
from .models import models  # noqa: F401  (register mappings)


def _production_guards() -> None:
    if not settings.is_production:
        return
    if settings.DATABASE_URL.startswith("sqlite"):
        raise RuntimeError("Production requires durable PostgreSQL; SQLite is refused")
    if settings.JWT_SECRET in ("", "dev-only-insecure-secret"):
        raise RuntimeError("Production requires a real JWT secret from the environment")
    if settings.SECURITY_SCAN_MODE == "disabled":
        raise RuntimeError("Production requires security scanning (mode 'disabled' refused)")
    if settings.JWT_SECRET == "dev-only-insecure-secret":
        raise RuntimeError("Production requires real secrets")


def _seed_system_admin_dev() -> None:
    """Dev/test convenience: ensure one SYSTEM_ADMIN exists for admin flows.
    Production admin provisioning is a deployment/secret-management concern."""
    if settings.is_production:
        return
    from sqlalchemy import select
    from .core.security import ROLE_SYSTEM_ADMIN, hash_password
    from .models.models import Users
    with engine.begin() as conn:
        pass  # ensure tables exist is handled by alembic/Base.create_all in tests
    from .db.session import SessionLocal
    db = SessionLocal()
    try:
        exists = db.execute(select(Users).where(Users.role == ROLE_SYSTEM_ADMIN)).scalars().first()
        if exists is None:
            db.add(Users(email="system-admin@example.com",
                         password_hash=hash_password("SystemAdmin#2026"),
                         full_name="System Admin", role=ROLE_SYSTEM_ADMIN, status="ACTIVE"))
            db.commit()
    finally:
        db.close()


def _seed_regulator_dev() -> None:
    """Dev/test convenience: one REGULATOR account for the read-only console."""
    if settings.is_production:
        return
    from sqlalchemy import select
    from .core.security import ROLE_REGULATOR, hash_password
    from .models.models import Users
    db = SessionLocal()
    try:
        exists = db.execute(select(Users).where(Users.role == ROLE_REGULATOR)).scalars().first()
        if exists is None:
            db.add(Users(email="regulator@example.com",
                         password_hash=hash_password("Regulator#2026"),
                         full_name="Regulatory Authority", role=ROLE_REGULATOR,
                         status="ACTIVE"))
            db.commit()
    finally:
        db.close()


def create_app() -> FastAPI:
    _production_guards()
    app = FastAPI(title="SecureHealth Care Platform", version="4.1",
                  docs_url="/api/docs", openapi_url="/api/openapi.json")

    register_error_handlers(app)

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        if request.url.path.startswith("/api/v1") and request.method != "OPTIONS":
            # Preflight requests are never counted; they are answered with CORS
            # headers by the outer CORS middleware (registered after this one).
            ip = request.client.host if request.client else "unknown"
            if request.url.path.startswith("/api/v1/auth"):
                ok = limiter.hit(f"auth:{ip}", settings.RATE_LIMIT_AUTH_PER_MIN)
            else:
                ok = limiter.hit(f"general:{ip}", settings.RATE_LIMIT_GENERAL_PER_MIN)
            if not ok:
                return rate_limited_response()
        return await call_next(request)

    # CORS is added LAST so it is the OUTERMOST middleware: even rate-limit 429
    # responses carry CORS headers and surface as clean RATE_LIMITED errors.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,  # explicit allowlist (TRD §14)
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    api_prefix = "/api/v1"
    app.include_router(auth.router, prefix=api_prefix)
    app.include_router(records.router, prefix=api_prefix)
    app.include_router(consents.router, prefix=api_prefix)
    app.include_router(misc.router, prefix=api_prefix)
    app.include_router(admin.router, prefix=api_prefix)
    app.include_router(federated.router, prefix=api_prefix)
    app.include_router(ledger.router, prefix=api_prefix)
    app.include_router(ai.router, prefix=api_prefix)
    app.include_router(regulator.router, prefix=api_prefix)

    @app.on_event("startup")
    def _startup() -> None:
        os.makedirs(settings.STORAGE_ROOT, exist_ok=True)      # protected bytes, outside web root
        os.makedirs(settings.QUARANTINE_ROOT, exist_ok=True)   # pre-scan holding area
        from .services import ledger as ledger_service
        from .services.ai_worker import start_worker as start_ai_worker
        from .services.ledger_outbox import start_worker
        from .services.seed_demo import seed_demo_accounts, seed_network
        if settings.is_production:
            return  # alembic migrations are the production schema authority
        Base.metadata.create_all(engine)
        _seed_system_admin_dev()
        _seed_regulator_dev()
        db = SessionLocal()
        try:
            seed_network(db)          # synthetic demo network (idempotent)
            seed_demo_accounts(db)    # ready-to-demo patient/doctor accounts
            ledger_service.ensure_genesis(db)  # GENESIS block exists before any event
            db.commit()
        finally:
            db.close()
        start_worker()                # durable outbox worker (dev/test thread)
        start_ai_worker()             # AI jobs + expiry sweep (dev/test thread)

    return app


app = create_app()
