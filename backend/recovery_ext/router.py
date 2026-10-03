from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.session import get_db
from backend.recovery_ext.flags import get_flags
from backend.recovery_ext.models import IncidentEventModel, IncidentRunModel
from backend.recovery_ext.approval_gate import router as approval_router

ext_router = APIRouter(
    prefix="/api",
    tags=["Recovery Engine Extensions"],
)
ext_router.include_router(approval_router, prefix="", tags=["Approval"])

@ext_router.get("/flags", status_code=status.HTTP_200_OK)
async def get_system_flags() -> dict[str, Any]:
    flags = get_flags()
    return {
        "enable_webhook_ingress": flags.enable_webhook_ingress,
        "enable_persistence": flags.enable_persistence,
        "enable_demo_scenarios": flags.enable_demo_scenarios,
        "enable_benchmark_view": flags.enable_benchmark_view,
    }

@ext_router.get("/benchmark/results", status_code=status.HTTP_200_OK)
async def get_benchmark_results() -> dict[str, Any]:
    flags = get_flags()
    if not flags.enable_benchmark_view:
        raise HTTPException(status_code=403, detail="Benchmark view disabled")
        
    import os
    import json
    path = "benchmark/results.json"
    if not os.path.exists(path):
        return {"exists": False}
        
    try:
        with open(path) as f:
            data = json.load(f)
        return {"exists": True, "results": data}
    except Exception as e:
        return {"exists": False, "error": str(e)}

@ext_router.get("/health", status_code=status.HTTP_200_OK)
async def api_health(session: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    from backend.config import get_settings
    from sqlalchemy import text
    import subprocess
    
    settings = get_settings()
    flags = get_flags()
    
    db_status = "ok"
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"
        
    docker_status = "ok"
    try:
        subprocess.run(["docker", "info"], check=True, capture_output=True, timeout=2)
    except Exception:
        docker_status = "error"
        
    return {
        "status": "ok" if db_status == "ok" and docker_status == "ok" else "degraded",
        "model_config_source": "env" if settings.nebius_api_key else "mock",
        "nebius_model": settings.nebius_model,
        "database": db_status,
        "docker": docker_status,
        "flags": flags.model_dump()
    }


@ext_router.get("/incidents", status_code=status.HTTP_200_OK)
async def list_incident_runs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retrieve persisted incident runs (Phase 1 durable persistence)."""
    flags = get_flags()
    if not flags.enable_persistence:
        return {"items": [], "total": 0, "persistence_enabled": False}

    stmt = select(IncidentRunModel).order_by(IncidentRunModel.created_at.desc()).offset(offset).limit(limit)
    res = await session.execute(stmt)
    runs = res.scalars().all()

    items = [
        {
            "id": r.id,
            "incident_id": r.incident_id,
            "repo": r.repo,
            "status": r.status,
            "risk_score": r.risk_score,
            "decision": r.decision,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in runs
    ]

    return {"items": items, "total": len(items), "persistence_enabled": True}


@ext_router.get("/incidents/{incident_id}/events", status_code=status.HTTP_200_OK)
async def get_incident_events(
    incident_id: str,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retrieve persisted events for a given incident run."""
    flags = get_flags()
    if not flags.enable_persistence:
        return {"incident_id": incident_id, "events": [], "persistence_enabled": False}

    stmt = select(IncidentEventModel).where(IncidentEventModel.incident_id == incident_id).order_by(IncidentEventModel.created_at.asc())
    res = await session.execute(stmt)
    evts = res.scalars().all()

    events = [
        {
            "id": e.id,
            "incident_id": e.incident_id,
            "node": e.node,
            "type": e.type,
            "payload": e.payload,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in evts
    ]

    return {"incident_id": incident_id, "events": events, "count": len(events), "persistence_enabled": True}
