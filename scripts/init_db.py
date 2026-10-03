import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.db.base import Base
from backend.db.session import engine
import backend.db.models  # Ensure models are loaded into Base metadata


async def init_tables():
    print("Creating database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Tables created successfully!")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_tables())
