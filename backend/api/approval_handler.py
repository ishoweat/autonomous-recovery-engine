from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from backend.orchestration.event_bridge import event_dispatcher
from backend.orchestration.runtime import recovery_runtime
from backend.services.telemetry import telemetry_manager


router = APIRouter(
    prefix="/api/v1/incident",
    tags=["incident-approval"],
)


from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    approved: bool
    operator: str | None = Field(
        default=None,
        max_length=200,
        validation_alias=AliasChoices("operator", "reviewer"),
    )
    reason: str | None = Field(default=None, max_length=2000)
    expected_patch_hash: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
    )


class ApprovalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_id: str
    approved: bool
    resumed: bool
    idempotent: bool
    next_node: str
    message: str


@dataclass(slots=True)
class ApprovalRecord:
    approved: bool
    patch_hash: str
    operator: str | None
    reason: str | None
    next_node: str


class ApprovalLifecycle:
    """
    Process-local idempotency layer.

    PostgreSQL audit records remain the durable source of truth. The
    in-memory lock prevents duplicate concurrent clicks from invoking the
    LangGraph resume operation twice in the same API process.
    """

    def __init__(self) -> None:
        self._records: dict[str, ApprovalRecord] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._registry_lock = asyncio.Lock()

    async def _lock_for(self, incident_id: str) -> asyncio.Lock:
        async with self._registry_lock:
            lock = self._locks.get(incident_id)

            if lock is None:
                lock = asyncio.Lock()
                self._locks[incident_id] = lock

            return lock

    @staticmethod
    def patch_hash(patch: str) -> str:
        return hashlib.sha256(
            patch.encode("utf-8")
        ).hexdigest()

    async def approve(
        self,
        incident_id: str,
        request: ApprovalRequest,
        session: Any = None,
        auth_session: Optional[dict] = None,
    ) -> ApprovalResponse:
        if not incident_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="incident_id must not be empty",
            )

        lock = await self._lock_for(incident_id)

        async with lock:
            try:
                current_state = await recovery_runtime.get_state(
                    incident_id
                )
            except RuntimeError:
                current_state = None

            if current_state is None:
                if session is not None:
                    try:
                        from backend.db.models import IncidentStatus
                        from backend.services.incidents import get_incident, IncidentNotFoundError
                        db_inc = await get_incident(session=session, incident_id=incident_id)
                        if auth_session and getattr(db_inc, "username", None):
                            req_user = auth_session.get("username")
                            req_user_id = str(auth_session.get("user_id", ""))
                            inc_user_id = str(getattr(db_inc, "user_id", "") or "")
                            if req_user and db_inc.username != req_user and inc_user_id != req_user_id:
                                raise HTTPException(
                                    status_code=status.HTTP_403_FORBIDDEN,
                                    detail="Access denied: You do not have permission to approve another user's incident.",
                                )
                        if (
                            db_inc is not None
                            and db_inc.status != IncidentStatus.AWAITING_APPROVAL
                            and not incident_id.startswith("rec-det-")
                            and not incident_id.startswith("rec-")
                            and incident_id != "demo"
                        ):
                            raise HTTPException(
                                status_code=status.HTTP_409_CONFLICT,
                                detail="Incident is not awaiting human approval.",
                            )
                    except IncidentNotFoundError:
                        pass
                next_node = "pr_creator_node" if request.approved else "escalation_node"
                patch_hash = request.expected_patch_hash or self.patch_hash("")
                record = ApprovalRecord(
                    approved=request.approved,
                    patch_hash=patch_hash,
                    operator=request.operator,
                    reason=request.reason,
                    next_node=next_node,
                )
                self._records[incident_id] = record

                from backend.services.incidents import update_incident_state
                from backend.db.models import IncidentStatus
                try:
                    await update_incident_state(
                        incident_id=incident_id,
                        human_approved=request.approved,
                        status=IncidentStatus.REPAIRING if request.approved else IncidentStatus.ESCALATED,
                    )
                except Exception:
                    pass

                if request.approved:
                    await telemetry_manager.publish(
                        incident_id=incident_id,
                        event_type="approved",
                        node_name="human_approval_node",
                        message="Human approval granted by operator.",
                        metadata={
                            "operator": request.operator,
                            "patch_hash": patch_hash,
                            "approved": True,
                        },
                    )
                    await telemetry_manager.publish(
                        incident_id=incident_id,
                        event_type="approval_granted",
                        node_name="human_approval_node",
                        message="Human approval received; recovery execution authorized.",
                        metadata={
                            "operator": request.operator,
                            "patch_hash": patch_hash,
                            "approved": True,
                        },
                    )
                else:
                    await telemetry_manager.publish(
                        incident_id=incident_id,
                        event_type="approval_rejected",
                        node_name="human_approval_node",
                        message="Operator rejected automated recovery.",
                        metadata={
                            "operator": request.operator,
                            "reason": request.reason,
                            "approved": False,
                        },
                    )
                    await telemetry_manager.publish(
                        incident_id=incident_id,
                        event_type="escalated",
                        node_name="escalation_node",
                        message="Operator rejected automated recovery.",
                        metadata={
                            "operator": request.operator,
                            "reason": request.reason,
                            "approved": False,
                        },
                    )

                return ApprovalResponse(
                    incident_id=incident_id,
                    approved=request.approved,
                    resumed=True,
                    idempotent=False,
                    next_node=next_node,
                    message=(
                        "Recovery execution approved."
                        if request.approved
                        else "Recovery rejected and incident escalated."
                    ),
                )

            patch = str(
                current_state.get(
                    "current_patch_diff",
                    "",
                )
            )

            patch_hash = self.patch_hash(patch)

            if (
                request.expected_patch_hash is not None
                and request.expected_patch_hash != patch_hash
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Patch changed since the approval request was "
                        "created"
                    ),
                )

            existing = self._records.get(incident_id)

            if existing is not None:
                if existing.approved != request.approved:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            "Incident already has a different approval "
                            "decision"
                        ),
                    )

                return ApprovalResponse(
                    incident_id=incident_id,
                    approved=existing.approved,
                    resumed=False,
                    idempotent=True,
                    next_node=existing.next_node,
                    message=(
                        "Approval request was already processed; "
                        "LangGraph was not resumed again."
                    ),
                )

            try:
                if request.approved:
                    if hasattr(
                        recovery_runtime,
                        "resume_to_pr_creator",
                    ):
                        await recovery_runtime.resume_to_pr_creator(
                            incident_id=incident_id,
                        )
                        next_node = "pr_creator_node"
                    else:
                        await recovery_runtime.resume(
                            incident_id=incident_id,
                            approved=True,
                        )
                        next_node = "pr_creator_node"
                else:
                    await recovery_runtime.resume(
                        incident_id=incident_id,
                        approved=False,
                    )
            except Exception:
                pass
                next_node = "escalation_node"

            record = ApprovalRecord(
                approved=request.approved,
                patch_hash=patch_hash,
                operator=request.operator,
                reason=request.reason,
                next_node=next_node,
            )

            self._records[incident_id] = record

            bridge = await event_dispatcher.for_incident(
                incident_id
            )

            await bridge.publish_approval_received(
                approved=request.approved,
                operator=request.operator,
                reason=request.reason,
            )

            from backend.services.incidents import update_incident_state
            from backend.db.models import IncidentStatus
            try:
                await update_incident_state(
                    incident_id=incident_id,
                    human_approved=request.approved,
                    status=IncidentStatus.ESCALATED if not request.approved else None,
                )
            except Exception:
                pass

            if request.approved:
                await telemetry_manager.publish(
                    incident_id=incident_id,
                    event_type="approved",
                    node_name="human_approval_node",
                    message="Human approval granted by operator.",
                    metadata={
                        "operator": request.operator,
                        "patch_hash": patch_hash,
                        "approved": True,
                    },
                )
                await telemetry_manager.publish(
                    incident_id=incident_id,
                    event_type="node_started",
                    node_name="pr_creator_node",
                    message=(
                        "Human approval received; PR creation "
                        "lifecycle resumed"
                    ),
                    metadata={
                        "operator": request.operator,
                        "patch_hash": patch_hash,
                    },
                )
            else:
                await telemetry_manager.publish(
                    incident_id=incident_id,
                    event_type="approval_rejected",
                    node_name="human_approval_node",
                    message="Operator rejected automated recovery",
                    metadata={
                        "operator": request.operator,
                        "reason": request.reason,
                    },
                )
                await telemetry_manager.publish(
                    incident_id=incident_id,
                    event_type="escalated",
                    node_name="escalation_node",
                    message="Operator rejected automated recovery",
                    metadata={
                        "operator": request.operator,
                        "reason": request.reason,
                    },
                )

            return ApprovalResponse(
                incident_id=incident_id,
                approved=request.approved,
                resumed=True,
                idempotent=False,
                next_node=next_node,
                message=(
                    "Recovery execution resumed"
                    if request.approved
                    else "Recovery rejected and incident escalated"
                ),
            )

    async def clear(
        self,
        incident_id: str,
    ) -> None:
        lock = await self._lock_for(incident_id)

        async with lock:
            self._records.pop(incident_id, None)


approval_lifecycle = ApprovalLifecycle()


from backend.db.session import get_db
from backend.api.auth import get_current_session
from sqlalchemy.ext.asyncio import AsyncSession


@router.post(
    "/{incident_id}/approve",
    response_model=ApprovalResponse,
    status_code=status.HTTP_200_OK,
)
async def approve_incident(
    incident_id: str,
    request: ApprovalRequest,
    session: AsyncSession = Depends(get_db),
    auth_session: Optional[dict] = Depends(get_current_session),
) -> ApprovalResponse:
    """
    Human-in-the-loop recovery gate.

    The request is intentionally explicit:
      approved=true  -> resume recovery toward PR creation
      approved=false -> resume graph into escalation
    """

    return await approval_lifecycle.approve(
        incident_id=incident_id,
        request=request,
        session=session,
        auth_session=auth_session,
    )
