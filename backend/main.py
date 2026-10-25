from __future__ import annotations

from contextlib import asynccontextmanager

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.approval_handler import router as approval_router
from backend.api.auth import router as auth_router, v1_auth_router
from backend.api.code_repair import router as code_repair_router
from backend.api.github_workspace import router as github_workspace_router, github_api_router
from backend.api.incidents import router as incident_router
from backend.api.learning import router as learning_router
from backend.api.remediate import router as remediate_router
from backend.api.roi import router as roi_router
from backend.api.v2 import router as v2_router
from backend.api.webhooks import router as webhook_router, v1_webhook_router
from backend.config import get_settings
from backend.db.base import Base
from backend.db.session import engine
from backend.orchestration.runtime import recovery_runtime


from backend.tools.sandbox_cleanup import startup_sandbox_cleanup



@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        startup_sandbox_cleanup()
    except Exception:
        pass

    settings = get_settings()

    if settings.environment == "development":
        try:
            async with engine.begin() as connection:
                await connection.run_sync(
                    Base.metadata.create_all
                )
                # Auto-ensure newly added columns on existing SQLite table
                if "sqlite" in settings.database_url:
                    for col in ("user_id", "username", "session_id"):
                        try:
                            await connection.exec_driver_sql(
                                f"ALTER TABLE incidents ADD COLUMN {col} VARCHAR(128)"
                            )
                        except Exception:
                            pass
                    try:
                        await connection.exec_driver_sql("ALTER TABLE incidents ADD COLUMN is_demo BOOLEAN DEFAULT FALSE")
                    except Exception:
                        pass
                    try:
                        await connection.exec_driver_sql("ALTER TABLE fix_records ADD COLUMN is_demo BOOLEAN DEFAULT FALSE")
                    except Exception:
                        pass
        except Exception:
            pass

    try:
        from backend.recovery_ext.db import init_ext_db
        await init_ext_db()
    except Exception:
        pass

    try:
        await recovery_runtime.start()
    except Exception:
        pass

    try:
        from backend.recovery_ext.flags import get_flags
        from backend.recovery_ext.event_bridge import start_webhook_worker
        flags = get_flags()
        if flags.enable_webhook_ingress:
            await start_webhook_worker()
            
        from backend.recovery_ext.merge_poller import start_merge_poller
        start_merge_poller()
    except Exception:
        pass

    try:
        yield
    finally:
        try:
            from backend.recovery_ext.event_bridge import stop_webhook_worker
            await stop_webhook_worker()
        except Exception:
            pass
        try:
            await recovery_runtime.stop()
        except Exception:
            pass
        try:
            await engine.dispose()
        except Exception:
            pass
        try:
            from backend.services.http_client import close_shared_client
            await close_shared_client()
        except Exception:
            pass


def create_app() -> FastAPI:
    settings = get_settings()

    application = FastAPI(
        title=settings.app_name,
        description=(
            "AI-driven stateful autonomous incident "
            "remediation engine."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    import os
    cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]
    for local_dev_url in ["http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3000", "http://127.0.0.1:3001"]:
        if local_dev_url not in cors_origins:
            cors_origins.append(local_dev_url)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    try:
        from backend.recovery_ext.rate_limit import RateLimitMiddleware
        application.add_middleware(RateLimitMiddleware)
    except ImportError:
        pass

    application.include_router(
        webhook_router
    )
    application.include_router(
        v1_webhook_router
    )

    from backend.recovery_ext.flags import get_flags
    flags = get_flags()
    if flags.enable_webhook_ingress:
        from backend.recovery_ext.webhook_ingress import router as ext_webhook_router
        application.include_router(ext_webhook_router)

    application.include_router(
        auth_router
    )
    application.include_router(
        v1_auth_router
    )

    application.include_router(
        approval_router
    )

    application.include_router(
        incident_router
    )

    from backend.api.incidents import plural_router
    application.include_router(
        plural_router
    )

    application.include_router(
        code_repair_router
    )

    application.include_router(
        github_workspace_router
    )

    application.include_router(
        github_api_router
    )

    application.include_router(
        learning_router
    )

    application.include_router(
        roi_router
    )

    application.include_router(
        v2_router
    )

    application.include_router(
        remediate_router
    )

    from backend.recovery_ext.router import ext_router
    application.include_router(
        ext_router
    )

    @application.get(
        "/health",
        tags=["System"],
    )
    async def health() -> dict[str, str]:
        from sqlalchemy import text
        from backend.db.session import AsyncSessionLocal
        db_status = "ok"
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
        except Exception:
            db_status = "error"

        github_configured = (
            "configured"
            if (settings.github_token or settings.github_webhook_secret or settings.github_client_id)
            else "unconfigured"
        )
        nebius_configured = (
            "configured"
            if (settings.nebius_api_key and settings.nebius_api_key != "your_nebius_api_key")
            else "configured" if settings.allow_mock_mode else "unconfigured"
        )

        overall_status = "ok" if db_status == "ok" else "degraded"

        return {
            "status": overall_status,
            "backend": "ok",
            "database": db_status,
            "github": github_configured,
            "nebius": nebius_configured,
            "realtime": "ok",
        }

    @application.get(
        "/ready",
        tags=["System"],
    )
    async def ready():
        from sqlalchemy import text
        from fastapi.responses import JSONResponse
        from backend.db.session import AsyncSessionLocal
        from backend.services.telemetry import telemetry_manager

        checks = {}
        is_ready = True

        # Database check
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as exc:
            checks["database"] = f"error: {exc}"
            is_ready = False

        # Recovery runtime check
        checks["recovery_runtime"] = (
            "ok" if recovery_runtime.graph is not None else "uninitialized"
        )
        if recovery_runtime.graph is None:
            is_ready = False

        # GitHub configuration check
        github_ok = bool(
            settings.github_token
            or settings.github_webhook_secret
            or (settings.github_client_id and settings.github_client_secret)
        )
        checks["github"] = "configured" if github_ok else "unconfigured"

        # Nebius LLM check
        nebius_ok = bool(
            settings.nebius_api_key and settings.nebius_api_key != "your_nebius_api_key"
        ) or settings.allow_mock_mode
        checks["nebius"] = "configured" if nebius_ok else "unconfigured"

        # Realtime check
        checks["realtime"] = "ok"

        payload = {
            "status": "ready" if is_ready else "not_ready",
            "checks": checks,
        }

        if not is_ready:
            return JSONResponse(
                status_code=503,
                content=payload,
            )

        return payload

    return application


app = create_app()
