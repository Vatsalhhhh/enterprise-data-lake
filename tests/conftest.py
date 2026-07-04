"""Shared pytest fixtures.

Tests that need a live Postgres connection use the same connection details
as the rest of the project (via .env / environment variables) and are
skipped automatically if no database is reachable, so `pytest` still runs
cleanly in environments without Docker running.
"""
import os
import sys

import pytest
from dotenv import load_dotenv

load_dotenv()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "catalog"))
sys.path.insert(0, os.path.join(ROOT, "api"))
sys.path.insert(0, os.path.join(ROOT, "generators"))


def _pg_available() -> bool:
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=os.getenv("POSTGRES_PORT", "5544"),
            dbname=os.getenv("POSTGRES_DB", "warehouse"),
            user=os.getenv("POSTGRES_USER", "warehouse"),
            password=os.getenv("POSTGRES_PASSWORD", "warehouse"),
            connect_timeout=3,
        )
        conn.close()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def pg_available() -> bool:
    return _pg_available()


def pytest_collection_modifyitems(config, items):
    if _pg_available():
        return
    skip_pg = pytest.mark.skip(reason="Postgres warehouse not reachable in this environment")
    for item in items:
        if "requires_pg" in item.keywords:
            item.add_marker(skip_pg)
