"""A lightweight metadata catalog, backed by DuckDB, that substitutes for
the AWS Glue Data Catalog in this local setup.

For each curated dataset we record: domain, dataset name, schema (as JSON),
partition keys, row count, and a last-updated timestamp. Athena would query
Glue's catalog to know what tables/partitions exist; here anything that
wants to know "what curated datasets exist and what do they look like"
queries this DuckDB table instead.
"""
from __future__ import annotations

import datetime as dt
import json
import os

import duckdb

DEFAULT_CATALOG_PATH = os.path.join(os.path.dirname(__file__), "catalog.duckdb")


class CatalogStore:
    def __init__(self, db_path: str = DEFAULT_CATALOG_PATH):
        self.db_path = db_path
        self._conn = duckdb.connect(db_path)
        self._init_schema()

    def _init_schema(self):
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dataset_catalog (
                domain VARCHAR,
                dataset_name VARCHAR,
                schema_json VARCHAR,
                partition_keys VARCHAR,
                row_count BIGINT,
                last_updated TIMESTAMP,
                PRIMARY KEY (domain, dataset_name)
            )
            """
        )

    def register_dataset(self, domain: str, dataset_name: str, schema: dict,
                          partition_keys: list, row_count: int):
        now = dt.datetime.utcnow()
        self._conn.execute(
            """
            INSERT INTO dataset_catalog (domain, dataset_name, schema_json, partition_keys, row_count, last_updated)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (domain, dataset_name) DO UPDATE SET
                schema_json = excluded.schema_json,
                partition_keys = excluded.partition_keys,
                row_count = excluded.row_count,
                last_updated = excluded.last_updated
            """,
            [domain, dataset_name, json.dumps(schema), json.dumps(partition_keys), row_count, now],
        )

    def get_dataset(self, domain: str, dataset_name: str):
        row = self._conn.execute(
            "SELECT domain, dataset_name, schema_json, partition_keys, row_count, last_updated "
            "FROM dataset_catalog WHERE domain = ? AND dataset_name = ?",
            [domain, dataset_name],
        ).fetchone()
        if row is None:
            return None
        return {
            "domain": row[0],
            "dataset_name": row[1],
            "schema": json.loads(row[2]),
            "partition_keys": json.loads(row[3]),
            "row_count": row[4],
            "last_updated": row[5],
        }

    def list_datasets(self):
        rows = self._conn.execute(
            "SELECT domain, dataset_name, schema_json, partition_keys, row_count, last_updated "
            "FROM dataset_catalog ORDER BY domain, dataset_name"
        ).fetchall()
        return [
            {
                "domain": r[0],
                "dataset_name": r[1],
                "schema": json.loads(r[2]),
                "partition_keys": json.loads(r[3]),
                "row_count": r[4],
                "last_updated": r[5],
            }
            for r in rows
        ]

    def close(self):
        self._conn.close()
