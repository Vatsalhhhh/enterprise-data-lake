"""Catalog + transform layer: the local substitute for an AWS Glue ETL job.

Reads the most recent raw CSV partition for each dataset from MinIO,
applies type coercion / cleaning, runs data-quality checks, dedupes,
writes curated Parquet back to MinIO under curated/<domain>/<dataset>/,
and registers the result in the DuckDB-backed catalog (catalog_store.py).

In a real AWS deployment this same transform logic (pandas/pyarrow calls)
would run as a Glue PySpark job (or an EMR/Athena CTAS), reading from and
writing to real S3 prefixes -- the I/O boundary (boto3 S3 client) is
exactly the part that would change.
"""
from __future__ import annotations

import io
import os
import sys

import boto3
import pandas as pd
from botocore.client import Config
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))

from schemas import DATASET_SPECS, DatasetSpec
from quality_checks import run_quality_checks, dedupe
from catalog_store import CatalogStore

load_dotenv()

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
BUCKET = os.getenv("MINIO_BUCKET", "data-lake")

# Order matters: parents must be transformed before children so that
# referential-integrity checks have something to check against.
TRANSFORM_ORDER = [
    "sales.regions", "sales.customers", "sales.orders", "sales.order_lines",
    "hr.employees", "hr.headcount_costs", "hr.attrition_events",
    "finance.budgets_by_department", "finance.revenue_by_month", "finance.gl_transactions",
    "inventory.sku_master", "inventory.stock_levels", "inventory.warehouse_movements",
    "marketing.campaigns", "marketing.spend_by_channel", "marketing.leads_by_campaign",
]

DATE_COLUMNS_BY_DTYPE = "date"


def get_client():
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def find_latest_partition_key(client, domain: str, dataset: str) -> str | None:
    prefix = f"raw/{domain}/{dataset}/"
    paginator = client.get_paginator("list_objects_v2")
    keys = []
    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    if not keys:
        return None
    # partition folders are dt=YYYY-MM-DD -- lexicographic sort works
    return sorted(keys)[-1]


def read_raw_csv(client, domain: str, dataset: str) -> pd.DataFrame | None:
    key = find_latest_partition_key(client, domain, dataset)
    if key is None:
        return None
    obj = client.get_object(Bucket=BUCKET, Key=key)
    body = obj["Body"].read()
    return pd.read_csv(io.BytesIO(body))


def coerce_types(df: pd.DataFrame, spec: DatasetSpec) -> pd.DataFrame:
    df = df.copy()
    for col, dtype in spec.columns.items():
        if col not in df.columns:
            continue
        if dtype == "date":
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
        elif dtype == "int":
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
        elif dtype == "float":
            df[col] = pd.to_numeric(df[col], errors="coerce").astype(float)
        elif dtype == "bool":
            df[col] = df[col].astype(str).str.lower().isin(["true", "1", "yes"])
        else:
            df[col] = df[col].astype("string")
    return df


def write_curated_parquet(client, df: pd.DataFrame, domain: str, dataset: str) -> str:
    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    buf.seek(0)
    key = f"curated/{domain}/{dataset}/{dataset}.parquet"
    client.put_object(Bucket=BUCKET, Key=key, Body=buf.getvalue())
    return key


def transform_all(verbose: bool = True):
    client = get_client()
    catalog = CatalogStore()

    parent_frames: dict[str, pd.DataFrame] = {}
    reports = []

    for full_name in TRANSFORM_ORDER:
        spec = DATASET_SPECS[full_name]
        raw_df = read_raw_csv(client, spec.domain, spec.name)
        if raw_df is None:
            if verbose:
                print(f"  [skip] no raw data found for {full_name}")
            continue

        cleaned = coerce_types(raw_df, spec)
        cleaned = dedupe(cleaned, spec)

        report = run_quality_checks(cleaned, spec, parent_frames)
        reports.append(report)
        if verbose:
            status = "PASS" if report.passed else "WARN"
            print(f"  [{status}] {full_name}: rows={report.row_count} "
                  f"nulls={report.null_violations} dupes={report.duplicate_key_count} "
                  f"fk={report.fk_violations}")

        parent_frames[full_name] = cleaned

        key = write_curated_parquet(client, cleaned, spec.domain, spec.name)
        schema_repr = {c: str(cleaned[c].dtype) for c in cleaned.columns}
        catalog.register_dataset(
            domain=spec.domain,
            dataset_name=spec.name,
            schema=schema_repr,
            partition_keys=[],
            row_count=len(cleaned),
        )
        if verbose:
            print(f"        curated -> s3://{BUCKET}/{key}")

    catalog.close()
    return reports


if __name__ == "__main__":
    print("Running catalog + transform (Glue-equivalent) pipeline...")
    reports = transform_all()
    n_failed = sum(1 for r in reports if not r.passed)
    print(f"\n{len(reports)} datasets processed, {n_failed} with quality warnings.")
