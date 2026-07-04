"""FastAPI query/analysis layer over the warehouse.

Exposes the pre-built cross-domain views as JSON endpoints, plus a
/analyze endpoint that takes a free-text cross-domain question and
returns a grounded natural-language comparison (LLM-backed if
OPENAI_API_KEY is set, deterministic template fallback otherwise).
"""
from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text

from db import get_engine
from analyze import analyze as run_analysis
from sql_guard import UnsafeQueryError

load_dotenv()

app = FastAPI(
    title="Enterprise Data Lake API",
    description="Cross-domain query and analysis layer over the warehouse.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    question: str


def _safe_records(df: pd.DataFrame) -> list[dict]:
    """Converts a DataFrame to JSON-safe records, mapping NaN/NaT to None.

    df.where(pd.notna(df), None) is not reliable for this: on a float64
    column, assigning None back through .where() gets silently re-cast to
    NaN instead of upcasting the column to object dtype, so a genuinely
    missing value (e.g. an inventory SKU with no stock on hand, so no
    computable turnover ratio) survives as NaN and crashes Starlette's
    JSON encoder (which disallows NaN) with a 500. Scanning the already
    materialized records and swapping NaN floats for None directly
    sidesteps that dtype behavior entirely.
    """
    records = df.to_dict(orient="records")
    for record in records:
        for key, value in record.items():
            if isinstance(value, float) and math.isnan(value):
                record[key] = None
    return records


def _query_to_records(sql: str) -> list[dict]:
    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn)
    return _safe_records(df)


@app.get("/")
def root():
    return {
        "service": "enterprise-data-lake-api",
        "status": "ok",
        "endpoints": [
            "/health", "/domains", "/views/revenue-vs-hr-cost",
            "/views/marketing-vs-sales", "/views/inventory-turns",
            "/views/department-pnl", "/analyze",
        ],
    }


@app.get("/health")
def health():
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"database unavailable: {exc}")


@app.get("/domains")
def domains():
    return {
        "domains": ["sales", "hr", "finance", "inventory", "marketing"],
        "cross_domain_views": [
            "vw_revenue_vs_hr_cost", "vw_revenue_vs_hr_cost_by_region",
            "vw_marketing_spend_vs_sales", "vw_inventory_turns_vs_sales",
            "vw_department_pnl",
        ],
    }


@app.get("/views/revenue-vs-hr-cost")
def revenue_vs_hr_cost(department: str | None = None, region: str | None = None):
    if region:
        sql = (
            "SELECT department, region_code, month_start, hr_cost, gl_revenue, cogs, gross_margin "
            "FROM vw_revenue_vs_hr_cost_by_region WHERE region_code = :region"
        )
        params = {"region": region}
        if department:
            sql += " AND department = :dept"
            params["dept"] = department
        sql += " ORDER BY month_start"
        engine = get_engine()
        with engine.connect() as conn:
            df = pd.read_sql(text(sql), conn, params=params)
        return _safe_records(df)

    sql = "SELECT department, month_start, hr_cost, gl_revenue, cogs, gross_margin FROM vw_revenue_vs_hr_cost"
    params = {}
    if department:
        sql += " WHERE department = :dept"
        params["dept"] = department
    sql += " ORDER BY month_start"
    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn, params=params)
    return _safe_records(df)


@app.get("/views/marketing-vs-sales")
def marketing_vs_sales(region: str | None = None):
    sql = "SELECT region_code, month_start, marketing_spend, sales_revenue, order_count FROM vw_marketing_spend_vs_sales"
    params = {}
    if region:
        sql += " WHERE region_code = :region"
        params["region"] = region
    sql += " ORDER BY month_start"
    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn, params=params)
    return _safe_records(df)


@app.get("/views/inventory-turns")
def inventory_turns(sku: str | None = None, region: str | None = None):
    sql = "SELECT sku, region_code, month_start, quantity_on_hand, outbound_qty, turnover_ratio FROM vw_inventory_turns_vs_sales WHERE 1=1"
    params = {}
    if sku:
        sql += " AND sku = :sku"
        params["sku"] = sku
    if region:
        sql += " AND region_code = :region"
        params["region"] = region
    sql += " ORDER BY month_start"
    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn, params=params)
    return _safe_records(df)


@app.get("/views/department-pnl")
def department_pnl(department: str | None = None):
    sql = "SELECT department, month_start, revenue, total_opex, budget_amount, hr_cost FROM vw_department_pnl"
    params = {}
    if department:
        sql += " WHERE department = :dept"
        params["dept"] = department
    sql += " ORDER BY month_start"
    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn, params=params)
    return _safe_records(df)


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    if not req.question or not req.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")
    try:
        result = run_analysis(req.question)
    except UnsafeQueryError as exc:
        raise HTTPException(status_code=400, detail=f"unsafe query rejected: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"analysis failed: {exc}")

    return {
        "question": result.question,
        "mode": result.mode,
        "views_used": result.views_used,
        "sql": result.sql,
        "answer": result.answer,
        "data_preview": result.data_preview[:20],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", "8000")),
        reload=True,
    )
