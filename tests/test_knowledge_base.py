import uuid
import pytest
from sqlalchemy import select

from backend.db.base import Base
from backend.db.models import KnowledgePattern
from backend.db.session import AsyncSessionLocal, engine
from backend.schemas.knowledge import KnowledgePatternCreate, KnowledgePatternResponse


@pytest.mark.asyncio
async def test_knowledge_pattern_model_crud():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        # Create a new learned pattern
        pattern = KnowledgePattern(
            incident_id="inc-test-1234",
            repository="owner/repo",
            error_type="KeyError",
            root_cause_summary="Missing key 'user_id' in authentication payload dictionary lookup",
            patch_pattern="payload.get('user_id') or raise ValueError('user_id is required')",
            confidence=0.95,
            file_path="sandbox/vulnerable_app/auth.py",
            pattern_metadata={"language": "python", "framework": "fastapi"},
        )
        session.add(pattern)
        await session.commit()
        await session.refresh(pattern)

        assert pattern.id is not None
        assert pattern.error_type == "KeyError"
        assert pattern.confidence == 0.95

        # Query the pattern
        result = await session.execute(
            select(KnowledgePattern).where(KnowledgePattern.incident_id == "inc-test-1234")
        )
        fetched = result.scalars().first()
        assert fetched is not None
        assert fetched.incident_id == "inc-test-1234"


        # Schema serialization
        schema = KnowledgePatternResponse.model_validate(fetched)
        assert schema.error_type == "KeyError"
        assert schema.root_cause_summary == pattern.root_cause_summary

        # Clean up
        await session.delete(fetched)
        await session.commit()
