"""Loads curated Parquet from the lake (MinIO) into the Postgres warehouse
as a star schema (dim_date, dim_department, dim_region + per-domain facts).

This is the local substitute for an Athena CTAS / Redshift COPY / Glue job
that would populate a real warehouse from an S3 curated zone. The curated
Parquet read here is byte-for-byte what a Redshift Spectrum or Athena query
would read directly from S3 in a real AWS deployment.
"""
from __future__ import annotations

import datetime as dt
import io
import os
import sys

import boto3
import pandas as pd
from botocore.client import Config
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
BUCKET = os.getenv("MINIO_BUCKET", "data-lake")

PG_HOST = os.getenv("POSTGRES_HOST", "localhost")
PG_PORT = os.getenv("POSTGRES_PORT", "5432")
PG_DB = os.getenv("POSTGRES_DB", "warehouse")
PG_USER = os.getenv("POSTGRES_USER", "warehouse")
PG_PASSWORD = os.getenv("POSTGRES_PASSWORD", "warehouse")

SCHEMA_SQL_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")

DEPARTMENTS = ["Sales", "Engineering", "Marketing", "Customer Support", "Operations", "Finance"]


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def get_engine():
    url = f"postgresql+psycopg2://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}"
    return create_engine(url)


def read_curated_parquet(client, domain: str, dataset: str) -> pd.DataFrame:
    key = f"curated/{domain}/{dataset}/{dataset}.parquet"
    obj = client.get_object(Bucket=BUCKET, Key=key)
    body = obj["Body"].read()
    return pd.read_parquet(io.BytesIO(body))


def apply_schema(engine):
    with open(SCHEMA_SQL_PATH) as f:
        sql = f.read()
    with engine.begin() as conn:
        conn.execute(text(sql))


def month_start(series: pd.Series) -> pd.Series:
    dts = pd.to_datetime(series)
    return dts.values.astype("datetime64[M]")


def build_dim_date(all_dates: list) -> pd.DataFrame:
    unique_dates = sorted(set(pd.to_datetime(d).date() for d in all_dates if pd.notna(d)))
    rows = []
    for d in unique_dates:
        rows.append({
            "date_key": d,
            "year": d.year,
            "month": d.month,
            "month_start": dt.date(d.year, d.month, 1),
            "quarter": (d.month - 1) // 3 + 1,
            "month_name": d.strftime("%B"),
        })
    return pd.DataFrame(rows)


def load_warehouse(verbose: bool = True):
    client = get_s3_client()
    engine = get_engine()

    if verbose:
        print("applying warehouse star schema...")
    apply_schema(engine)

    # --- read curated datasets ---
    regions = read_curated_parquet(client, "sales", "regions")
    customers = read_curated_parquet(client, "sales", "customers")
    orders = read_curated_parquet(client, "sales", "orders")
    employees = read_curated_parquet(client, "hr", "employees")
    headcount = read_curated_parquet(client, "hr", "headcount_costs")
    gl = read_curated_parquet(client, "finance", "gl_transactions")
    budgets = read_curated_parquet(client, "finance", "budgets_by_department")
    stock = read_curated_parquet(client, "inventory", "stock_levels")
    movements = read_curated_parquet(client, "inventory", "warehouse_movements")
    campaigns = read_curated_parquet(client, "marketing", "campaigns")
    spend = read_curated_parquet(client, "marketing", "spend_by_channel")
    leads = read_curated_parquet(client, "marketing", "leads_by_campaign")

    # --- dim_date ---
    all_dates = list(orders["order_date"]) + list(headcount["month"]) + list(gl["month"]) \
        + list(budgets["month"]) + list(stock["month"]) + list(movements["month"]) \
        + list(spend["month"]) + list(leads["month"])
    dim_date = build_dim_date(all_dates)

    dim_department = pd.DataFrame({"department": DEPARTMENTS})
    dim_region = regions.rename(columns={"country_group": "country_group", "sub_region": "sub_region"})

    # --- fact_sales ---
    fact_sales = orders.copy()
    fact_sales["month_start"] = pd.to_datetime(fact_sales["order_date"]).values.astype("datetime64[M]")
    fact_sales["month_start"] = pd.to_datetime(fact_sales["month_start"]).dt.date
    fact_sales = fact_sales[["order_id", "customer_id", "region_code", "order_date",
                              "month_start", "order_total", "order_cost", "status"]]

    # --- fact_hr_cost ---
    fact_hr_cost = headcount.rename(columns={"month": "month_start"})
    fact_hr_cost = fact_hr_cost[["department", "region_code", "month_start", "headcount",
                                  "salary_cost", "benefits_cost", "total_cost"]]

    # --- fact_finance_gl ---
    fact_finance_gl = gl.rename(columns={"month": "month_start"})
    fact_finance_gl = fact_finance_gl[["txn_id", "department", "region_code", "month_start",
                                        "account_code", "account_name", "amount"]]

    # --- fact_finance_budget ---
    fact_finance_budget = budgets.rename(columns={"month": "month_start"})
    fact_finance_budget = fact_finance_budget[["department", "month_start", "budget_amount"]]

    # --- fact_inventory_stock ---
    fact_inventory_stock = stock.rename(columns={"month": "month_start"})
    fact_inventory_stock = fact_inventory_stock[["sku", "region_code", "month_start",
                                                  "quantity_on_hand", "unit_cost"]]

    # --- fact_inventory_movement ---
    fact_inventory_movement = movements.rename(columns={"month": "month_start"})
    fact_inventory_movement = fact_inventory_movement[["movement_id", "sku", "region_code",
                                                        "month_start", "movement_type", "quantity"]]

    # --- fact_marketing_spend --- (join channel/region from campaigns onto spend rows for consistency)
    fact_marketing_spend = spend.rename(columns={"month": "month_start"})
    fact_marketing_spend = fact_marketing_spend[["campaign_id", "channel", "region_code",
                                                  "month_start", "spend_amount"]]

    # --- fact_marketing_leads ---
    fact_marketing_leads = leads.rename(columns={"month": "month_start"})
    fact_marketing_leads = fact_marketing_leads[["lead_id", "campaign_id", "region_code",
                                                  "month_start", "converted"]]

    tables = [
        ("dim_date", dim_date),
        ("dim_department", dim_department),
        ("dim_region", dim_region),
        ("fact_sales", fact_sales),
        ("fact_hr_cost", fact_hr_cost),
        ("fact_finance_gl", fact_finance_gl),
        ("fact_finance_budget", fact_finance_budget),
        ("fact_inventory_stock", fact_inventory_stock),
        ("fact_inventory_movement", fact_inventory_movement),
        ("fact_marketing_spend", fact_marketing_spend),
        ("fact_marketing_leads", fact_marketing_leads),
    ]

    # Table order above already puts dims before facts so FK constraints
    # are satisfied naturally as each table loads.
    for name, df in tables:
        df.to_sql(name, engine, if_exists="append", index=False, method="multi", chunksize=2000)
        if verbose:
            print(f"  loaded {name}: {len(df)} rows")

    if verbose:
        print("warehouse load complete.")


if __name__ == "__main__":
    load_warehouse()
