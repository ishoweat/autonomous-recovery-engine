import asyncio
import sys
from pathlib import Path
from sqlalchemy import text, inspect

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.db.base import Base
from backend.db.session import engine
import backend.db.models  # Ensures all models are registered


async def migrate():
    """
    Idempotently creates all tables, indexes, and adds any new columns to existing tables.
    Works seamlessly on both PostgreSQL and SQLite.
    """
    print("Executing database migration for Repository Context System...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        def _check_and_add_columns(connection):
            insp = inspect(connection)
            if "incidents" in insp.get_table_names():
                existing_cols = {c["name"] for c in insp.get_columns("incidents")}
                
                new_columns = [
                    ("repository_owner", "VARCHAR(128) DEFAULT '' NOT NULL"),
                    ("repository_name", "VARCHAR(128) DEFAULT '' NOT NULL"),
                    ("repository_full_name", "VARCHAR(255) DEFAULT '' NOT NULL"),
                    ("repository_url", "VARCHAR(512) DEFAULT '' NOT NULL"),
                    ("default_branch", "VARCHAR(255) DEFAULT 'main' NOT NULL"),
                    ("source_branch", "VARCHAR(255) DEFAULT '' NOT NULL"),
                    ("workflow_run_id", "VARCHAR(128) DEFAULT '' NOT NULL"),
                ]
                for col_name, col_type in new_columns:
                    if col_name not in existing_cols:
                        print(f"Adding column '{col_name}' to 'incidents' table...")
                        try:
                            connection.execute(text(f"ALTER TABLE incidents ADD COLUMN {col_name} {col_type}"))
                        except Exception as e:
                            print(f"Notice when adding {col_name}: {e}")

        await conn.run_sync(_check_and_add_columns)

    print("Migration completed: new columns verified/created!")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(migrate())
