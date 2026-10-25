from __future__ import annotations

from typing import Any
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import KnowledgePattern
from backend.db.session import AsyncSessionLocal


async def find_similar_patterns(
    *,
    error_type: str | None = None,
    repository: str | None = None,
    limit: int = 5,
    session: AsyncSession | None = None,
) -> list[dict[str, Any]]:
    """
    Search the Knowledge Base for matching root causes and patch patterns
    from previous successful remediations.
    """
    if not error_type and not repository:
        return []

    async def _query(s: AsyncSession) -> list[dict[str, Any]]:
        query = select(KnowledgePattern)
        
        if error_type and repository:
            # First attempt: match both error_type and repository
            specific_query = (
                query.where(
                    KnowledgePattern.error_type.ilike(f"%{error_type}%"),
                    KnowledgePattern.repository == repository,
                )
                .order_by(desc(KnowledgePattern.confidence), desc(KnowledgePattern.created_at))
                .limit(limit)
            )
            result = await s.execute(specific_query)
            rows = result.scalars().all()
            if rows:
                return [_pattern_to_dict(r) for r in rows]

        # Second attempt: match error_type across any repository
        if error_type:
            general_query = (
                query.where(KnowledgePattern.error_type.ilike(f"%{error_type}%"))
                .order_by(desc(KnowledgePattern.confidence), desc(KnowledgePattern.created_at))
                .limit(limit)
            )
            result = await s.execute(general_query)
            rows = result.scalars().all()
            if rows:
                return [_pattern_to_dict(r) for r in rows]

        return []

    if session is not None:
        return await _query(session)

    try:
        async with AsyncSessionLocal() as db_session:
            return await _query(db_session)
    except Exception:
        return []


async def record_learned_pattern(
    *,
    error_type: str,
    root_cause_summary: str,
    patch_pattern: str,
    confidence: float = 1.0,
    repository: str = "",
    incident_id: str | None = None,
    file_path: str | None = None,
    pattern_metadata: dict[str, Any] | None = None,
    session: AsyncSession | None = None,
) -> KnowledgePattern:
    """
    Store a newly validated fix into the knowledge base for future memory recall.
    """
    pattern = KnowledgePattern(
        incident_id=incident_id,
        repository=repository,
        error_type=error_type,
        root_cause_summary=root_cause_summary,
        patch_pattern=patch_pattern,
        confidence=min(1.0, max(0.0, confidence)),
        file_path=file_path,
        pattern_metadata={
            **(pattern_metadata or {}),
            "patch_hash": str(hash(patch_pattern)) if patch_pattern else None,
        },
    )

    if session is not None:
        session.add(pattern)
        await session.flush()
        return pattern

    async with AsyncSessionLocal() as db_session:
        db_session.add(pattern)
        await db_session.commit()
        await db_session.refresh(pattern)
        return pattern


def _pattern_to_dict(p: KnowledgePattern) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "incident_id": p.incident_id,
        "repository": p.repository,
        "error_type": p.error_type,
        "root_cause_summary": p.root_cause_summary,
        "patch_pattern": p.patch_pattern,
        "confidence": p.confidence,
        "file_path": p.file_path,
        "pattern_metadata": p.pattern_metadata,
        "created_at": p.created_at.isoformat() if p.created_at else "",
    }
