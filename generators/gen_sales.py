"""Generates synthetic Sales domain CSVs: customers, regions, orders, order_lines."""
from __future__ import annotations

import os
import random
import datetime as dt

import numpy as np
import pandas as pd

from common import (
    START_DATE, END_DATE, REGIONS, month_range,
    STORY_REGION, STORY_MARGIN_HIT,
)

OUT_DIR = os.path.join(os.path.dirname(__file__), "output", "sales")
os.makedirs(OUT_DIR, exist_ok=True)

random.seed(1001)
np.random.seed(1001)

PRODUCTS = [
    ("SKU-1001", "Widget Pro", 49.99, 18.00),
    ("SKU-1002", "Widget Lite", 24.99, 9.00),
    ("SKU-1003", "Gadget Max", 129.99, 55.00),
    ("SKU-1004", "Gadget Mini", 79.99, 32.00),
    ("SKU-1005", "Connector Kit", 14.99, 4.50),
    ("SKU-1006", "Premium Bundle", 249.99, 105.00),
    ("SKU-1007", "Starter Pack", 39.99, 15.00),
    ("SKU-1008", "Enterprise License", 999.00, 200.00),
]

N_CUSTOMERS = 400


def gen_regions():
    rows = []
    for code, country_group, sub in REGIONS:
        rows.append({"region_code": code, "country_group": country_group, "sub_region": sub})
    return pd.DataFrame(rows)


def gen_customers():
    rows = []
    for i in range(1, N_CUSTOMERS + 1):
        region = random.choice(REGIONS)[0]
        signup = START_DATE + dt.timedelta(days=random.randint(0, 700))
        segment = random.choices(["SMB", "Mid-Market", "Enterprise"], weights=[0.6, 0.3, 0.1])[0]
        rows.append({
            "customer_id": f"CUST-{i:05d}",
            "region_code": region,
            "segment": segment,
            "signup_date": signup.isoformat(),
        })
    return pd.DataFrame(rows)


def gen_orders_and_lines(customers: pd.DataFrame):
    orders = []
    lines = []
    order_seq = 1
    line_seq = 1

    months = list(month_range(START_DATE, END_DATE))
    for month in months:
        # base order volume with mild growth trend + seasonality
        month_idx = months.index(month)
        trend = 1.0 + month_idx * 0.006
        seasonality = 1.15 if month.month in (11, 12) else (0.9 if month.month in (1, 2) else 1.0)
        base_orders = int(180 * trend * seasonality)

        for _ in range(base_orders):
            cust = customers.sample(1).iloc[0]
            region = cust["region_code"]
            day = random.randint(1, 28)
            order_date = dt.date(month.year, month.month, day)

            n_lines = random.choices([1, 2, 3, 4], weights=[0.5, 0.3, 0.15, 0.05])[0]
            order_total = 0.0
            order_cost = 0.0

            # Story: elevated refunds/discounts for support-heavy region starting Q3 2024
            discount_rate = 0.0
            if region == STORY_REGION and order_date >= STORY_MARGIN_HIT:
                discount_rate = np.random.uniform(0.08, 0.18)
            else:
                discount_rate = np.random.uniform(0.0, 0.04)

            for _ in range(n_lines):
                sku, name, price, cost = random.choice(PRODUCTS)
                qty = random.randint(1, 5)
                gross = price * qty
                net = gross * (1 - discount_rate)
                order_total += net
                order_cost += cost * qty

                lines.append({
                    "order_line_id": f"OL-{line_seq:07d}",
                    "order_id": f"ORD-{order_seq:07d}",
                    "sku": sku,
                    "product_name": name,
                    "quantity": qty,
                    "unit_price": price,
                    "unit_cost": cost,
                    "discount_rate": round(discount_rate, 4),
                    "line_net_amount": round(net, 2),
                })
                line_seq += 1

            orders.append({
                "order_id": f"ORD-{order_seq:07d}",
                "customer_id": cust["customer_id"],
                "region_code": region,
                "order_date": order_date.isoformat(),
                "order_total": round(order_total, 2),
                "order_cost": round(order_cost, 2),
                "status": random.choices(
                    ["completed", "completed", "completed", "refunded", "cancelled"],
                    weights=[0.7, 0.15, 0.1, 0.03, 0.02],
                )[0],
            })
            order_seq += 1

    return pd.DataFrame(orders), pd.DataFrame(lines)


def main():
    regions_df = gen_regions()
    customers_df = gen_customers()
    orders_df, lines_df = gen_orders_and_lines(customers_df)

    regions_df.to_csv(os.path.join(OUT_DIR, "regions.csv"), index=False)
    customers_df.to_csv(os.path.join(OUT_DIR, "customers.csv"), index=False)
    orders_df.to_csv(os.path.join(OUT_DIR, "orders.csv"), index=False)
    lines_df.to_csv(os.path.join(OUT_DIR, "order_lines.csv"), index=False)

    print(f"sales: regions={len(regions_df)} customers={len(customers_df)} "
          f"orders={len(orders_df)} order_lines={len(lines_df)}")


if __name__ == "__main__":
    main()
