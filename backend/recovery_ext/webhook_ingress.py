from fastapi import APIRouter, Request, HTTPException, status, Depends
import hmac
import hashlib
from fastapi.responses import JSONResponse
import logging

from backend.recovery_ext.flags import get_flags
from backend.config import get_settings
from backend.recovery_ext.event_bridge import webhook_queue

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/webhooks",
    tags=["Webhooks"],
)

async def verify_github_signature(request: Request):
    settings = get_settings()
    secret = settings.github_webhook_secret or ""
    
    signature_header = request.headers.get("x-hub-signature-256")
    if not signature_header:
        raise HTTPException(status_code=401, detail="Missing signature")
        
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > settings.webhook_max_body_bytes:
        raise HTTPException(status_code=413, detail="Payload too large")
    
    body = await request.body()
    expected_signature = "sha256=" + hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(expected_signature, signature_header):
        raise HTTPException(status_code=401, detail="Invalid signature")

@router.post("/github")
async def github_webhook(
    request: Request,
    _ = Depends(verify_github_signature)
):
    flags = get_flags()
    if not flags.enable_webhook_ingress:
        return JSONResponse(status_code=202, content={"reason": "Webhook ingress disabled"})
        
    event_type = request.headers.get("x-github-event")
    delivery_id = request.headers.get("x-github-delivery")
    
    if event_type not in ("workflow_run", "pull_request"):
        return JSONResponse(status_code=202, content={"reason": f"Ignored event type: {event_type}"})
        
    payload = await request.json()
    action = payload.get("action")
    repo = payload.get("repository", {}).get("full_name", "")
    
    if flags.public_demo_mode and not repo.startswith("demo/scenarios"):
        return JSONResponse(status_code=403, content={"reason": "Arbitrary repos are blocked in public demo mode."})
    
    if event_type == "workflow_run":
        if action != "completed":
            return JSONResponse(status_code=202, content={"reason": f"Ignored action: {action}"})
        workflow_run = payload.get("workflow_run", {})
        conclusion = workflow_run.get("conclusion")
        if conclusion != "failure":
            return JSONResponse(status_code=202, content={"reason": f"Ignored conclusion: {conclusion}"})
            
        head_branch = workflow_run.get("head_branch", "")
        if head_branch.startswith("ai-recovery/"):
            return JSONResponse(status_code=202, content={"reason": "Ignored bot branch"})
            
        head_sha = workflow_run.get("head_sha")
        if not head_sha:
            return JSONResponse(status_code=400, content={"reason": "Missing head_sha"})
    
    elif event_type == "pull_request":
        if action != "closed":
            return JSONResponse(status_code=202, content={"reason": f"Ignored action: {action}"})
        pull_request = payload.get("pull_request", {})
        if not pull_request.get("merged"):
            return JSONResponse(status_code=202, content={"reason": "PR closed but not merged"})
        
    from sqlalchemy import select
    from backend.db.session import AsyncSessionLocal
    from backend.recovery_ext.models import WebhookDeliveryModel
    
    async with AsyncSessionLocal() as session:
        # Check delivery dedup
        result = await session.execute(
            select(WebhookDeliveryModel).where(WebhookDeliveryModel.delivery_id == delivery_id)
        )
        if result.scalars().first():
            return JSONResponse(status_code=202, content={"reason": "Duplicate delivery ID ignored"})
            
        # Check commit dedup for workflow_runs
        if event_type == "workflow_run":
            # For simplicity, we can just look up if an incident already exists for this sha
            from backend.db.models import Incident
            existing = await session.execute(
                select(Incident).where(Incident.commit_sha == head_sha)
            )
            if existing.scalars().first():
                return JSONResponse(status_code=202, content={"reason": f"Duplicate incident for commit {head_sha}"})
            
        # Register the delivery ID
        session.add(WebhookDeliveryModel(delivery_id=delivery_id))
        await session.commit()
        
    # Queue for event bridge processing
    item = {
        "delivery_id": delivery_id,
        "payload": payload,
    }
    
    try:
        webhook_queue.put_nowait(item)
    except Exception as e:
        logger.error(f"Webhook queue full or error: {e}")
        return JSONResponse(status_code=503, content={"reason": "Queue full"})
        
    return {"status": "accepted", "delivery_id": delivery_id}
