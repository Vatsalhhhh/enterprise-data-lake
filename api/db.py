"""Database connection helper shared by API endpoints."""
from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()

PG_HOST = os.getenv("POSTGRES_HOST", "localhost")
PG_PORT = os.getenv("POSTGRES_PORT", "5544")
PG_DB = os.getenv("POSTGRES_DB", "warehouse")
PG_USER = os.getenv("POSTGRES_USER", "warehouse")
PG_PASSWORD = os.getenv("POSTGRES_PASSWORD", "warehouse")

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        url = f"postgresql+psycopg2://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}"
        _engine = create_engine(url, pool_pre_ping=True)
    return _engine
