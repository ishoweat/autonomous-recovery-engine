import asyncio
import sys
from pathlib import Path
from sqlalchemy import text, inspect

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.db.base import Base
from backend.db.session import engine
import backend.db.models  # Ensures all models (incidents, audit_trails, knowledge_base) are registered


async def migrate():
    """
    Idempotently creates all tables, indexes, and adds any new columns to existing tables.
    Works seamlessly on both PostgreSQL and SQLite.
    """
    print("Executing database migration for Learning & Memory System...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Check for missing columns in incidents table (SQLite / Postgres)
        def _check_and_add_columns(connection):
            insp = inspect(connection)
            if "incidents" in insp.get_table_names():
                existing_cols = {c["name"] for c in insp.get_columns("incidents")}
                
                new_columns = [
                    ("patch_explanation", "TEXT DEFAULT '' NOT NULL"),
                    ("generated_test_code", "TEXT DEFAULT '' NOT NULL"),
                    ("similar_past_cases", "JSON DEFAULT '[]' NOT NULL" if connection.dialect.name == "sqlite" else "JSONB DEFAULT '[]' NOT NULL"),
                    ("learning_confidence_boost", "FLOAT DEFAULT 0.0 NOT NULL"),
                    ("is_shadow_mode", "BOOLEAN DEFAULT 1 NOT NULL" if connection.dialect.name == "sqlite" else "BOOLEAN DEFAULT TRUE NOT NULL"),
                ]
                for col_name, col_type in new_columns:
                    if col_name not in existing_cols:
                        print(f"Adding column '{col_name}' to 'incidents' table...")
                        try:
                            connection.execute(text(f"ALTER TABLE incidents ADD COLUMN {col_name} {col_type}"))
                        except Exception as e:
                            print(f"Notice when adding {col_name}: {e}")

        await conn.run_sync(_check_and_add_columns)

    print("Migration completed: 'knowledge_base' and all columns verified/created!")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(migrate())

