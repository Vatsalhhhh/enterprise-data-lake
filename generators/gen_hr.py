"""Generates synthetic HR domain CSVs: employees, headcount_costs, attrition_events."""
from __future__ import annotations

import os
import random
import datetime as dt

import numpy as np
import pandas as pd

from common import (
    START_DATE, END_DATE, DEPARTMENTS, REGIONS, month_range,
    STORY_DEPARTMENT, STORY_REGION, STORY_START,
)

OUT_DIR = os.path.join(os.path.dirname(__file__), "output", "hr")
os.makedirs(OUT_DIR, exist_ok=True)

random.seed(2002)
np.random.seed(2002)

BASE_SALARY = {
    "Sales": 78000,
    "Engineering": 118000,
    "Marketing": 82000,
    "Customer Support": 54000,
    "Operations": 66000,
    "Finance": 92000,
}

REGION_CODES = [r[0] for r in REGIONS]


def gen_employees():
    rows = []
    emp_id = 1
    for dept in DEPARTMENTS:
        for region in REGION_CODES:
            n = random.randint(4, 14)
            for _ in range(n):
                hire_date = START_DATE + dt.timedelta(days=random.randint(0, 900))
                rows.append({
                    "employee_id": f"EMP-{emp_id:05d}",
                    "department": dept,
                    "region_code": region,
                    "hire_date": hire_date.isoformat(),
                    "job_level": random.choice(["IC1", "IC2", "IC3", "Manager", "Senior Manager"]),
                })
                emp_id += 1
    return pd.DataFrame(rows)


def gen_headcount_costs(employees: pd.DataFrame):
    rows = []
    months = list(month_range(START_DATE, END_DATE))

    for dept in DEPARTMENTS:
        for region in REGION_CODES:
            headcount_base = len(employees[(employees.department == dept) & (employees.region_code == region)])
            if headcount_base == 0:
                continue
            base_monthly_salary = BASE_SALARY[dept] / 12

            for i, month in enumerate(months):
                headcount = headcount_base
                extra_hires = 0
                overtime_multiplier = 1.0

                # Story: Customer Support in NA-EAST ramps headcount + overtime
                # starting April 2024, driving cost up well before the
                # matching margin squeeze shows up in Finance next quarter.
                if dept == STORY_DEPARTMENT and region == STORY_REGION and month >= STORY_START:
                    months_into_story = (month.year - STORY_START.year) * 12 + (month.month - STORY_START.month)
                    extra_hires = min(8, 1 + months_into_story)
                    overtime_multiplier = 1.0 + min(0.35, 0.05 * months_into_story)

                headcount_effective = headcount + extra_hires
                salary_cost = headcount_effective * base_monthly_salary * overtime_multiplier
                benefits_cost = salary_cost * np.random.uniform(0.22, 0.28)
                # mild general wage inflation over time
                inflation = 1.0 + (i * 0.0025)
                salary_cost *= inflation
                benefits_cost *= inflation

                rows.append({
                    "department": dept,
                    "region_code": region,
                    "month": month.isoformat(),
                    "headcount": headcount_effective,
                    "salary_cost": round(salary_cost, 2),
                    "benefits_cost": round(benefits_cost, 2),
                    "total_cost": round(salary_cost + benefits_cost, 2),
                })
    return pd.DataFrame(rows)


def gen_attrition_events(employees: pd.DataFrame):
    rows = []
    event_id = 1
    for _, emp in employees.iterrows():
        # ~18% annual attrition chance, scaled to the observed window
        if random.random() < 0.30:
            hire = dt.date.fromisoformat(emp["hire_date"])
            earliest = hire + dt.timedelta(days=60)
            if earliest >= END_DATE:
                continue
            span_days = (END_DATE - earliest).days
            term_date = earliest + dt.timedelta(days=random.randint(0, span_days))
            reason = random.choices(
                ["voluntary", "involuntary", "retirement"],
                weights=[0.7, 0.25, 0.05],
            )[0]

            # Story: elevated voluntary attrition in the story dept/region
            # right before the cost ramp -- burnout driving backfill hiring.
            if (emp["department"] == STORY_DEPARTMENT and emp["region_code"] == STORY_REGION
                    and dt.date(2024, 1, 1) <= term_date <= dt.date(2024, 6, 30)):
                reason = "voluntary"

            rows.append({
                "event_id": f"ATTR-{event_id:05d}",
                "employee_id": emp["employee_id"],
                "department": emp["department"],
                "region_code": emp["region_code"],
                "termination_date": term_date.isoformat(),
                "reason": reason,
            })
            event_id += 1
    return pd.DataFrame(rows)


def main():
    employees_df = gen_employees()
    headcount_costs_df = gen_headcount_costs(employees_df)
    attrition_df = gen_attrition_events(employees_df)

    employees_df.to_csv(os.path.join(OUT_DIR, "employees.csv"), index=False)
    headcount_costs_df.to_csv(os.path.join(OUT_DIR, "headcount_costs.csv"), index=False)
    attrition_df.to_csv(os.path.join(OUT_DIR, "attrition_events.csv"), index=False)

    print(f"hr: employees={len(employees_df)} headcount_costs={len(headcount_costs_df)} "
          f"attrition_events={len(attrition_df)}")


if __name__ == "__main__":
    main()
