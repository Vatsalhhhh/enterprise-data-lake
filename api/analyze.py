"""Cross-domain natural-language analysis.

Two paths:
  1. If OPENAI_API_KEY is set, use langchain + openai to pick a registered
     view and either summarize it directly or generate a safe read-only SQL
     query against the warehouse, then have the model turn the real numbers
     into a grounded natural-language comparison.
  2. If no API key is set (the default for anyone cloning this repo without
     paying for an OpenAI key), fall back to a deterministic, keyword-based
     template engine that picks the same registered views by keyword match,
     runs the same read-only SQL against Postgres, and formats a comparison
     using an f-string template. This keeps the whole project runnable and
     demoable at zero cost.

Both paths are grounded: neither ever fabricates numbers. They only narrate
numbers that were actually returned by a SQL query against the warehouse.
"""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import text

from db import get_engine
from sql_guard import validate_readonly_sql, UnsafeQueryError
from views_registry import REGISTERED_VIEWS

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


@dataclass
class AnalysisResult:
    question: str
    mode: str  # "llm" or "fallback"
    views_used: list = field(default_factory=list)
    sql: str = ""
    answer: str = ""
    data_preview: list = field(default_factory=list)


def _safe_records(df: pd.DataFrame) -> list:
    """Converts a DataFrame to JSON-safe records, mapping NaN/NaT to None.

    Standard JSON has no NaN literal, so a view with legitimately missing
    data (e.g. AVG() over a SKU that's had zero stock all period, so its
    turnover ratio is undefined) would otherwise crash the API's JSON
    encoder with a 500 rather than just reporting the row as unknown.

    df.where(pd.notnull(df), None) is not reliable for this: on a float64
    column, assigning None back through .where() gets silently re-cast to
    NaN rather than upcasting the column to object dtype. Scanning the
    already-materialized records and swapping NaN floats for None directly
    sidesteps that dtype behavior entirely.
    """
    records = df.to_dict(orient="records")
    for record in records:
        for key, value in record.items():
            if isinstance(value, float) and math.isnan(value):
                record[key] = None
    return records


def _score_view(question: str, view_key: str, meta: dict) -> int:
    q = question.lower()
    score = 0
    for kw in meta["keywords"]:
        if kw in q:
            score += 1
    return score


def pick_views(question: str, top_n: int = 1) -> list[str]:
    scored = [
        (key, _score_view(question, key, meta))
        for key, meta in REGISTERED_VIEWS.items()
    ]
    scored = [s for s in scored if s[1] > 0]
    if not scored:
        # default: the most general cross-domain view
        return ["vw_revenue_vs_hr_cost"]
    scored.sort(key=lambda s: s[1], reverse=True)
    return [key for key, _ in scored[:top_n]]


def run_readonly_query(sql: str) -> pd.DataFrame:
    safe_sql = validate_readonly_sql(sql)
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(text(safe_sql), conn)


# ---------------------------------------------------------------------
# Deterministic fallback (no API key required)
# ---------------------------------------------------------------------

def _fallback_revenue_vs_hr(question: str) -> AnalysisResult:
    sql = (
        "SELECT department, "
        "ROUND(SUM(hr_cost), 2) AS total_hr_cost, "
        "ROUND(SUM(gl_revenue), 2) AS total_revenue, "
        "ROUND(SUM(gross_margin), 2) AS total_gross_margin "
        "FROM vw_revenue_vs_hr_cost "
        "GROUP BY department ORDER BY total_hr_cost DESC"
    )
    df = run_readonly_query(sql)

    lines = ["Revenue vs HR cost by department (full history):"]
    for _, row in df.iterrows():
        ratio = (row["total_hr_cost"] / row["total_revenue"] * 100) if row["total_revenue"] else 0
        lines.append(
            f"  - {row['department']}: HR cost ${row['total_hr_cost']:,.0f} vs "
            f"revenue ${row['total_revenue']:,.0f} (HR cost is {ratio:.1f}% of revenue), "
            f"gross margin ${row['total_gross_margin']:,.0f}."
        )

    top_cost_dept = df.iloc[0]["department"] if len(df) else "N/A"
    lines.append(
        f"\n{top_cost_dept} carries the highest HR cost of any department in the warehouse. "
        "If HR cost is rising while gross margin for the same department is falling in a "
        "given quarter, that's the clearest sign cost growth is outpacing revenue -- check "
        "the region-level breakdown (vw_revenue_vs_hr_cost_by_region) to localize it."
    )

    return AnalysisResult(
        question=question, mode="fallback",
        views_used=["vw_revenue_vs_hr_cost"], sql=sql,
        answer="\n".join(lines),
        data_preview=_safe_records(df),
    )


def _fallback_marketing_vs_sales(question: str) -> AnalysisResult:
    sql = (
        "SELECT region_code, "
        "ROUND(SUM(marketing_spend), 2) AS total_spend, "
        "ROUND(SUM(sales_revenue), 2) AS total_revenue "
        "FROM vw_marketing_spend_vs_sales "
        "GROUP BY region_code ORDER BY total_spend DESC"
    )
    df = run_readonly_query(sql)
    lines = ["Marketing spend vs sales revenue by region (full history):"]
    for _, row in df.iterrows():
        roi = (row["total_revenue"] / row["total_spend"]) if row["total_spend"] else 0
        lines.append(
            f"  - {row['region_code']}: spend ${row['total_spend']:,.0f} -> "
            f"revenue ${row['total_revenue']:,.0f} (revenue-to-spend ratio {roi:.1f}x)."
        )
    return AnalysisResult(
        question=question, mode="fallback",
        views_used=["vw_marketing_spend_vs_sales"], sql=sql,
        answer="\n".join(lines),
        data_preview=_safe_records(df),
    )


def _fallback_inventory_vs_sales(question: str) -> AnalysisResult:
    sql = (
        "SELECT sku, "
        "ROUND(AVG(turnover_ratio), 3) AS avg_turnover_ratio, "
        "SUM(outbound_qty) AS total_outbound_qty "
        "FROM vw_inventory_turns_vs_sales "
        "GROUP BY sku ORDER BY avg_turnover_ratio DESC NULLS LAST"
    )
    df = run_readonly_query(sql)
    lines = ["Inventory turnover vs sales velocity by SKU (full history):"]
    for _, row in df.iterrows():
        ratio = row["avg_turnover_ratio"]
        ratio_txt = f"{ratio}" if pd.notna(ratio) else "no data (no stock on hand in this period)"
        lines.append(
            f"  - {row['sku']}: average monthly turnover ratio {ratio_txt}, "
            f"total outbound units {int(row['total_outbound_qty']):,}."
        )
    return AnalysisResult(
        question=question, mode="fallback",
        views_used=["vw_inventory_turns_vs_sales"], sql=sql,
        answer="\n".join(lines),
        data_preview=_safe_records(df),
    )


def _fallback_department_pnl(question: str) -> AnalysisResult:
    sql = (
        "SELECT department, "
        "ROUND(SUM(revenue), 2) AS total_revenue, "
        "ROUND(SUM(total_opex), 2) AS total_opex, "
        "ROUND(SUM(budget_amount), 2) AS total_budget, "
        "ROUND(SUM(hr_cost), 2) AS total_hr_cost "
        "FROM vw_department_pnl GROUP BY department ORDER BY total_revenue DESC"
    )
    df = run_readonly_query(sql)
    lines = ["Department P&L summary (full history):"]
    for _, row in df.iterrows():
        variance = row["total_opex"] - row["total_budget"] if pd.notna(row["total_budget"]) else None
        variance_txt = f", opex vs budget variance ${variance:,.0f}" if variance is not None else ""
        lines.append(
            f"  - {row['department']}: revenue ${row['total_revenue']:,.0f}, "
            f"opex ${row['total_opex']:,.0f}{variance_txt}, HR cost ${row['total_hr_cost']:,.0f}."
        )
    return AnalysisResult(
        question=question, mode="fallback",
        views_used=["vw_department_pnl"], sql=sql,
        answer="\n".join(lines),
        data_preview=_safe_records(df),
    )


FALLBACK_HANDLERS = {
    "vw_revenue_vs_hr_cost": _fallback_revenue_vs_hr,
    "vw_revenue_vs_hr_cost_by_region": _fallback_revenue_vs_hr,
    "vw_marketing_spend_vs_sales": _fallback_marketing_vs_sales,
    "vw_inventory_turns_vs_sales": _fallback_inventory_vs_sales,
    "vw_department_pnl": _fallback_department_pnl,
}


def analyze_fallback(question: str) -> AnalysisResult:
    views = pick_views(question, top_n=1)
    handler = FALLBACK_HANDLERS.get(views[0], _fallback_revenue_vs_hr)
    return handler(question)


# ---------------------------------------------------------------------
# LLM-backed path (requires OPENAI_API_KEY)
# ---------------------------------------------------------------------

def analyze_with_llm(question: str) -> AnalysisResult:
    from langchain_openai import ChatOpenAI

    views = pick_views(question, top_n=2)
    view_descriptions = "\n".join(
        f"- {v}: {REGISTERED_VIEWS[v]['description']} (columns: {', '.join(REGISTERED_VIEWS[v]['columns'])})"
        for v in views
    )

    llm = ChatOpenAI(model=OPENAI_MODEL, api_key=OPENAI_API_KEY, temperature=0)

    sql_prompt = (
        "You are a data analyst writing PostgreSQL. You may ONLY query these "
        f"pre-registered views:\n{view_descriptions}\n\n"
        "Write a single read-only SELECT statement (optionally with a CTE) "
        "that best answers the user's question below, using GROUP BY/aggregate "
        "functions to keep the result small (under 30 rows). Return ONLY the "
        "SQL statement, no explanation, no markdown fences, no semicolon.\n\n"
        f"Question: {question}"
    )
    sql_response = llm.invoke(sql_prompt).content.strip()
    sql_response = re.sub(r"^```sql|^```|```$", "", sql_response, flags=re.MULTILINE).strip()

    try:
        df = run_readonly_query(sql_response)
    except UnsafeQueryError:
        # if the model produced something unsafe or invalid, fall back to
        # the deterministic path rather than fail the request
        return analyze_fallback(question)

    data_csv = df.to_csv(index=False)
    narrate_prompt = (
        "You are a data analyst. Using ONLY the real numbers in the CSV data "
        "below (never invent numbers not present in it), write a concise, "
        "grounded natural-language comparison that answers the question. "
        "Cite specific figures from the data.\n\n"
        f"Question: {question}\n\nData:\n{data_csv}"
    )
    answer = llm.invoke(narrate_prompt).content.strip()

    return AnalysisResult(
        question=question, mode="llm", views_used=views, sql=sql_response,
        answer=answer, data_preview=_safe_records(df),
    )


def analyze(question: str) -> AnalysisResult:
    if OPENAI_API_KEY:
        try:
            return analyze_with_llm(question)
        except Exception:
            # any LLM/runtime failure degrades gracefully to the deterministic path
            return analyze_fallback(question)
    return analyze_fallback(question)
