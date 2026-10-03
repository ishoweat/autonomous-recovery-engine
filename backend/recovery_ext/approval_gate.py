from typing import Any
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from datetime import datetime, timezone
import logging

from sqlalchemy import text
from backend.db.session import AsyncSessionLocal
from backend.services.incidents import get_incident, update_incident_state
from backend.db.models import IncidentStatus
from backend.orchestration.runtime import recovery_runtime
from backend.recovery_ext.flags import get_flags
from backend.orchestration.telemetry import emit_node_event
from langgraph.types import interrupt

logger = logging.getLogger(__name__)

router = APIRouter()

class ApprovalDecisionRequest(BaseModel):
    decision: str
    operator: str

async def init_approvals_table():
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("""
                CREATE TABLE IF NOT EXISTS approvals (
                    incident_id VARCHAR PRIMARY KEY,
                    decision VARCHAR NOT NULL,
                    operator VARCHAR NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    resolved_at TIMESTAMP WITH TIME ZONE
                )
            """)
        )
        await session.commit()

async def pause_for_approval(state: dict[str, Any]) -> bool:
    """
    Pause the pipeline to wait for operator approval in Mission Control.
    Returns True if approved, False if rejected.
    """
    incident_id = state["incident_id"]

    await init_approvals_table()

    # Set run status AWAITING_APPROVAL
    await update_incident_state(
        incident_id=incident_id,
        status=IncidentStatus.AWAITING_APPROVAL,
    )

    # Store a row in approvals (pending state)
    async with AsyncSessionLocal() as session:
        # Upsert pending
        await session.execute(
            text("""
                INSERT INTO approvals (incident_id, decision, operator)
                VALUES (:id, 'pending', 'system')
                ON CONFLICT (incident_id) DO UPDATE 
                SET decision = 'pending', resolved_at = NULL
            """),
            {"id": incident_id}
        )
        await session.commit()

    # Emit [APPROVAL_GATE] hold event
    await emit_node_event(
        incident_id=incident_id,
        event_type="approval_gate",
        node_name="approval_gate",
        message="[APPROVAL_GATE] hold: Pipeline paused awaiting operator decision.",
        metadata={"stage": "approval"},
        retry_count=state.get("retry_count", 0),
    )

    import asyncio
    import os
    
    timeout_seconds = int(os.environ.get("APPROVAL_TIMEOUT_SECONDS", "900"))

    async def timeout_task():
        await asyncio.sleep(timeout_seconds)
        async with AsyncSessionLocal() as db_session:
            result = await db_session.execute(
                text("SELECT decision FROM approvals WHERE incident_id = :id"),
                {"id": incident_id}
            )
            row = result.fetchone()
            if row and row[0] == "pending":
                # Timeout happened
                await db_session.execute(
                    text("""
                        UPDATE approvals 
                        SET decision = 'reject', operator = 'system_timeout', resolved_at = :now
                        WHERE incident_id = :id
                    """),
                    {"id": incident_id, "now": datetime.now(timezone.utc)}
                )
                await db_session.commit()
                
                flags = get_flags()
                if not flags.enable_block_escalation:
                    await update_incident_state(incident_id=incident_id, status=IncidentStatus.FAILED)
                
                try:
                    await recovery_runtime.resume(incident_id=incident_id, approved=False)
                except Exception:
                    pass

    asyncio.create_task(timeout_task())

    # Pause execution
    approved = interrupt(
        {
            "type": "recovery_approval",
            "incident_id": incident_id,
        }
    )

    if not isinstance(approved, bool):
        # Fallback handling in case of dict return or auto-resume
        if isinstance(approved, dict):
            approved = approved.get("approved", False)
        else:
            approved = False

    return approved


@router.post("/incidents/{incident_id}/approval")
async def submit_approval(
    incident_id: str,
    request: ApprovalDecisionRequest,
):
    flags = get_flags()
    if not flags.enable_approval_gate:
        raise HTTPException(status_code=400, detail="Approval gate is not enabled")

    async with AsyncSessionLocal() as session:
        try:
            incident = await get_incident(session=session, incident_id=incident_id)
        except Exception:
            incident = None
            
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    if incident.status != IncidentStatus.AWAITING_APPROVAL:
        raise HTTPException(status_code=409, detail="Incident is not awaiting approval")

    decision = request.decision.lower()
    if decision not in ["approve", "reject"]:
        raise HTTPException(status_code=400, detail="Decision must be 'approve' or 'reject'")

    approved = (decision == "approve")

    await init_approvals_table()

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("SELECT decision FROM approvals WHERE incident_id = :id"),
            {"id": incident_id}
        )
        row = result.fetchone()
        
        if row and row[0] != "pending":
            if row[0] == decision:
                return {"status": "success", "decision": decision, "note": "idempotent"}
            else:
                raise HTTPException(status_code=409, detail="Different decision already recorded")

        await session.execute(
            text("""
                UPDATE approvals 
                SET decision = :dec, operator = :op, resolved_at = :now
                WHERE incident_id = :id
            """),
            {
                "dec": decision, 
                "op": request.operator, 
                "now": datetime.now(timezone.utc),
                "id": incident_id
            }
        )
        await session.commit()

    if not approved and not flags.enable_block_escalation:
        await update_incident_state(incident_id=incident_id, status=IncidentStatus.FAILED)

    try:
        await recovery_runtime.resume(incident_id=incident_id, approved=approved)
    except Exception as e:
        logger.error(f"Error resuming graph for {incident_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to resume pipeline")

    return {"status": "success", "decision": decision}
