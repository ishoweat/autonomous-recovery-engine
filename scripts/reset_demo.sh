#!/bin/bash
set -e

echo "Starting ARE Demo Reset..."

# 1. Reset Database tables (SQLite or Postgres)
# If using SQLite locally (backend/local_aegis.db)
if [ -f "backend/local_aegis.db" ]; then
    echo "Resetting SQLite database..."
    sqlite3 backend/local_aegis.db "DELETE FROM incidents;"
    sqlite3 backend/local_aegis.db "DELETE FROM system_analytics;"
    sqlite3 backend/local_aegis.db "DELETE FROM knowledge_patterns;"
    sqlite3 backend/local_aegis.db "DELETE FROM fix_records;"
    sqlite3 backend/local_aegis.db "DELETE FROM audit_events;"
    echo "SQLite database reset."
fi

# 2. Clear temp directories
echo "Clearing temporary recovery directories..."
rm -rf /tmp/recovery/* || true

echo "Demo Reset Complete! The Autonomous Recovery Engine is ready for the judges."
