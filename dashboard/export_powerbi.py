"""Exports clean, flat CSVs of every cross-domain view (plus core facts)
into dashboard/exports/powerbi/ so anyone who wants a real Power BI Desktop
report can load them directly via Get Data > Text/CSV -- no Postgres
connection required on the Power BI side.
"""
from __future__ import annotations

import os

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

PG_HOST = os.getenv("POSTGRES_HOST", "localhost")
PG_PORT = os.getenv("POSTGRES_PORT", "5544")
PG_DB = os.getenv("POSTGRES_DB", "warehouse")
PG_USER = os.getenv("POSTGRES_USER", "warehouse")
PG_PASSWORD = os.getenv("POSTGRES_PASSWORD", "warehouse")

OUT_DIR = os.path.join(os.path.dirname(__file__), "exports", "powerbi")
os.makedirs(OUT_DIR, exist_ok=True)

EXPORTS = {
    "revenue_vs_hr_cost.csv": "SELECT * FROM vw_revenue_vs_hr_cost ORDER BY department, month_start",
    "revenue_vs_hr_cost_by_region.csv": "SELECT * FROM vw_revenue_vs_hr_cost_by_region ORDER BY department, region_code, month_start",
    "marketing_spend_vs_sales.csv": "SELECT * FROM vw_marketing_spend_vs_sales ORDER BY region_code, month_start",
    "inventory_turns_vs_sales.csv": "SELECT * FROM vw_inventory_turns_vs_sales ORDER BY sku, region_code, month_start",
    "department_pnl.csv": "SELECT * FROM vw_department_pnl ORDER BY department, month_start",
    "dim_date.csv": "SELECT * FROM dim_date ORDER BY date_key",
    "dim_department.csv": "SELECT * FROM dim_department",
    "dim_region.csv": "SELECT * FROM dim_region",
}


def main():
    url = f"postgresql+psycopg2://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}"
    engine = create_engine(url)

    for filename, sql in EXPORTS.items():
        with engine.connect() as conn:
            df = pd.read_sql(text(sql), conn)
        out_path = os.path.join(OUT_DIR, filename)
        df.to_csv(out_path, index=False)
        print(f"exported {out_path} ({len(df)} rows)")


if __name__ == "__main__":
    main()
