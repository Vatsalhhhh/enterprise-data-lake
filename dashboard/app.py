"""Streamlit dashboard -- the local substitute for a Power BI report.

Tabs per domain (Sales, HR, Finance, Inventory, Marketing) plus a
cross-domain comparison tab with a chat box that hits the FastAPI
/analyze endpoint. Clean per-domain CSV exports are also written to
dashboard/exports/powerbi/ so anyone who wants an actual Power BI Desktop
report can load them directly (File > Get Data > Text/CSV).
"""
from __future__ import annotations

import os
import sys

import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
PG_HOST = os.getenv("POSTGRES_HOST", "localhost")
PG_PORT = os.getenv("POSTGRES_PORT", "5544")
PG_DB = os.getenv("POSTGRES_DB", "warehouse")
PG_USER = os.getenv("POSTGRES_USER", "warehouse")
PG_PASSWORD = os.getenv("POSTGRES_PASSWORD", "warehouse")

st.set_page_config(page_title="Enterprise Data Lake", layout="wide")


@st.cache_resource
def get_engine():
    url = f"postgresql+psycopg2://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}"
    return create_engine(url)


@st.cache_data(ttl=300)
def query(sql: str) -> pd.DataFrame:
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn)


st.title("Enterprise Data Lake -- Cross-Domain Analytics")
st.caption(
    "Sales, HR, Finance, Inventory, and Marketing data landed in a MinIO-backed "
    "lake, cataloged and cleaned, loaded into a Postgres warehouse star schema, "
    "and explored here. See the README for the honest AWS-service mapping."
)

tabs = st.tabs(["Sales", "HR", "Finance", "Inventory", "Marketing", "Cross-Domain Analysis"])

# ---------------- Sales ----------------
with tabs[0]:
    st.header("Sales")
    try:
        df = query(
            "SELECT region_code, month_start, SUM(order_total) AS revenue, COUNT(*) AS orders "
            "FROM fact_sales WHERE status <> 'cancelled' GROUP BY region_code, month_start ORDER BY month_start"
        )
        fig = px.line(df, x="month_start", y="revenue", color="region_code", title="Monthly Revenue by Region")
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(df, use_container_width=True)
    except Exception as exc:
        st.error(f"Could not load sales data: {exc}")

# ---------------- HR ----------------
with tabs[1]:
    st.header("HR")
    try:
        df = query(
            "SELECT department, month_start, SUM(headcount) AS headcount, SUM(total_cost) AS total_cost "
            "FROM fact_hr_cost GROUP BY department, month_start ORDER BY month_start"
        )
        fig = px.line(df, x="month_start", y="total_cost", color="department", title="Monthly HR Cost by Department")
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(df, use_container_width=True)
    except Exception as exc:
        st.error(f"Could not load HR data: {exc}")

# ---------------- Finance ----------------
with tabs[2]:
    st.header("Finance")
    try:
        df = query(
            "SELECT department, month_start, revenue, total_opex, budget_amount FROM vw_department_pnl ORDER BY month_start"
        )
        fig = px.line(df, x="month_start", y="revenue", color="department", title="Monthly Revenue by Department")
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(df, use_container_width=True)
    except Exception as exc:
        st.error(f"Could not load finance data: {exc}")

# ---------------- Inventory ----------------
with tabs[3]:
    st.header("Inventory")
    try:
        df = query(
            "SELECT sku, region_code, month_start, quantity_on_hand, turnover_ratio "
            "FROM vw_inventory_turns_vs_sales ORDER BY month_start"
        )
        fig = px.line(df, x="month_start", y="turnover_ratio", color="sku", title="Inventory Turnover Ratio by SKU")
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(df, use_container_width=True)
    except Exception as exc:
        st.error(f"Could not load inventory data: {exc}")

# ---------------- Marketing ----------------
with tabs[4]:
    st.header("Marketing")
    try:
        df = query(
            "SELECT region_code, month_start, marketing_spend, sales_revenue FROM vw_marketing_spend_vs_sales ORDER BY month_start"
        )
        fig = px.line(df, x="month_start", y="marketing_spend", color="region_code", title="Monthly Marketing Spend by Region")
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(df, use_container_width=True)
    except Exception as exc:
        st.error(f"Could not load marketing data: {exc}")

# ---------------- Cross-Domain Analysis ----------------
with tabs[5]:
    st.header("Cross-Domain Analysis")
    st.markdown(
        "Ask a cross-domain question in plain English, e.g. *\"Compare HR costs "
        "with revenue\"* or *\"How does marketing spend compare to sales by "
        "region?\"*. Answers are grounded in real warehouse numbers -- if no "
        "`OPENAI_API_KEY` is configured, a deterministic template engine answers "
        "instead of an LLM."
    )

    try:
        df = query(
            "SELECT department, region_code, month_start, hr_cost, gross_margin "
            "FROM vw_revenue_vs_hr_cost_by_region WHERE department = 'Customer Support' AND region_code = 'NA-EAST' "
            "ORDER BY month_start"
        )
        fig = px.line(df, x="month_start", y=["hr_cost", "gross_margin"],
                      title="Customer Support / NA-EAST: HR Cost vs Gross Margin")
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "This is the engineered cross-domain story in the sample data: rising HR "
            "cost in Customer Support (NA-EAST) from Q2 2024 precedes a margin squeeze "
            "the following quarter."
        )
    except Exception as exc:
        st.warning(f"Could not load story chart: {exc}")

    question = st.text_input("Ask a cross-domain question", value="Compare HR costs with revenue")
    if st.button("Analyze"):
        try:
            resp = requests.post(f"{API_BASE_URL}/analyze", json={"question": question}, timeout=30)
            resp.raise_for_status()
            result = resp.json()
            st.info(f"Mode: {result['mode']} | Views used: {', '.join(result['views_used'])}")
            st.write(result["answer"])
            with st.expander("SQL used"):
                st.code(result["sql"], language="sql")
            if result["data_preview"]:
                st.dataframe(pd.DataFrame(result["data_preview"]), use_container_width=True)
        except Exception as exc:
            st.error(f"Could not reach analysis API at {API_BASE_URL}: {exc}")

st.divider()
st.caption(
    "Data lake: MinIO (S3-compatible) | Catalog/transform: DuckDB + pandas/pyarrow "
    "(Glue-equivalent) | Warehouse: Postgres | Dashboard: Streamlit (Power BI-equivalent)"
)
