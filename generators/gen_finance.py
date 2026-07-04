"""Generates synthetic Finance domain CSVs: gl_transactions, budgets_by_department, revenue_by_month."""
from __future__ import annotations

import os
import random
import datetime as dt

import numpy as np
import pandas as pd

from common import (
    START_DATE, END_DATE, DEPARTMENTS, REGIONS, month_range,
    STORY_DEPARTMENT, STORY_REGION, STORY_MARGIN_HIT,
)

OUT_DIR = os.path.join(os.path.dirname(__file__), "output", "finance")
os.makedirs(OUT_DIR, exist_ok=True)

random.seed(3003)
np.random.seed(3003)

REGION_CODES = [r[0] for r in REGIONS]

GL_ACCOUNTS = [
    ("4000", "Revenue"),
    ("5000", "Cost of Goods Sold"),
    ("6000", "Salaries & Benefits"),
    ("6100", "Marketing Spend"),
    ("6200", "Facilities"),
    ("6300", "Professional Services"),
    ("6400", "Travel & Entertainment"),
]

BASE_DEPT_BUDGET_MONTHLY = {
    "Sales": 180000,
    "Engineering": 260000,
    "Marketing": 150000,
    "Customer Support": 95000,
    "Operations": 120000,
    "Finance": 110000,
}


def gen_budgets():
    rows = []
    months = list(month_range(START_DATE, END_DATE))
    for dept in DEPARTMENTS:
        annual_growth = np.random.uniform(0.02, 0.06)
        for i, month in enumerate(months):
            year_offset = (month.year - START_DATE.year) + (month.month - 1) / 12
            budget = BASE_DEPT_BUDGET_MONTHLY[dept] * (1 + annual_growth) ** year_offset
            rows.append({
                "department": dept,
                "month": month.isoformat(),
                "budget_amount": round(budget, 2),
            })
    return pd.DataFrame(rows)


def gen_revenue_by_month():
    rows = []
    months = list(month_range(START_DATE, END_DATE))
    for region in REGION_CODES:
        base = np.random.uniform(220000, 480000)
        for i, month in enumerate(months):
            trend = 1.0 + i * 0.007
            seasonality = 1.2 if month.month in (11, 12) else (0.85 if month.month in (1, 2) else 1.0)
            noise = np.random.normal(1.0, 0.04)
            revenue = base * trend * seasonality * noise

            # Story: revenue growth for the story region stalls starting
            # the margin-hit quarter, compounding the cost pressure.
            if region == STORY_REGION and month >= STORY_MARGIN_HIT:
                revenue *= 0.94

            rows.append({
                "region_code": region,
                "month": month.isoformat(),
                "revenue": round(revenue, 2),
            })
    return pd.DataFrame(rows)


def gen_gl_transactions(revenue_df: pd.DataFrame):
    rows = []
    txn_id = 1
    months = list(month_range(START_DATE, END_DATE))

    for dept in DEPARTMENTS:
        for region in REGION_CODES:
            for month in months:
                # Revenue and COGS entries derived loosely from region revenue,
                # split across departments for realism (Sales/Marketing/Ops get
                # the lion's share of revenue-linked postings).
                region_rev_row = revenue_df[(revenue_df.region_code == region) & (revenue_df.month == month.isoformat())]
                region_rev = float(region_rev_row["revenue"].iloc[0]) if len(region_rev_row) else 0.0
                dept_share = {
                    "Sales": 0.45, "Marketing": 0.15, "Operations": 0.15,
                    "Engineering": 0.10, "Customer Support": 0.10, "Finance": 0.05,
                }[dept]
                dept_revenue = region_rev * dept_share / len(REGION_CODES) * len(REGION_CODES)  # already per-region
                dept_revenue = region_rev * dept_share

                cogs_rate = 0.42
                # Story: COGS/discount-driven margin erosion for the story
                # dept/region a quarter after the HR cost ramp began.
                if dept == STORY_DEPARTMENT and region == STORY_REGION and month >= STORY_MARGIN_HIT:
                    months_in = (month.year - STORY_MARGIN_HIT.year) * 12 + (month.month - STORY_MARGIN_HIT.month)
                    cogs_rate = min(0.68, 0.42 + 0.03 * (months_in + 1))

                cogs = dept_revenue * cogs_rate

                rows.append({"txn_id": f"GL-{txn_id:07d}", "department": dept, "region_code": region,
                             "month": month.isoformat(), "account_code": "4000", "account_name": "Revenue",
                             "amount": round(dept_revenue, 2)})
                txn_id += 1
                rows.append({"txn_id": f"GL-{txn_id:07d}", "department": dept, "region_code": region,
                             "month": month.isoformat(), "account_code": "5000", "account_name": "Cost of Goods Sold",
                             "amount": round(-cogs, 2)})
                txn_id += 1

                # A handful of opex postings per department/month/account
                for code, name in GL_ACCOUNTS[2:]:
                    base_amt = {
                        "6000": BASE_DEPT_BUDGET_MONTHLY[dept] * 0.55,
                        "6100": BASE_DEPT_BUDGET_MONTHLY[dept] * 0.10 if dept == "Marketing" else BASE_DEPT_BUDGET_MONTHLY[dept] * 0.02,
                        "6200": BASE_DEPT_BUDGET_MONTHLY[dept] * 0.08,
                        "6300": BASE_DEPT_BUDGET_MONTHLY[dept] * 0.06,
                        "6400": BASE_DEPT_BUDGET_MONTHLY[dept] * 0.03,
                    }[code]
                    amt = base_amt * np.random.uniform(0.85, 1.15)
                    rows.append({"txn_id": f"GL-{txn_id:07d}", "department": dept, "region_code": region,
                                 "month": month.isoformat(), "account_code": code, "account_name": name,
                                 "amount": round(-amt, 2)})
                    txn_id += 1

    return pd.DataFrame(rows)


def main():
    budgets_df = gen_budgets()
    revenue_df = gen_revenue_by_month()
    gl_df = gen_gl_transactions(revenue_df)

    budgets_df.to_csv(os.path.join(OUT_DIR, "budgets_by_department.csv"), index=False)
    revenue_df.to_csv(os.path.join(OUT_DIR, "revenue_by_month.csv"), index=False)
    gl_df.to_csv(os.path.join(OUT_DIR, "gl_transactions.csv"), index=False)

    print(f"finance: budgets={len(budgets_df)} revenue_by_month={len(revenue_df)} gl_transactions={len(gl_df)}")


if __name__ == "__main__":
    main()
