"""Generates synthetic Inventory domain CSVs: sku_master, stock_levels, warehouse_movements."""
from __future__ import annotations

import os
import random
import datetime as dt

import numpy as np
import pandas as pd

from common import START_DATE, END_DATE, REGIONS, month_range

OUT_DIR = os.path.join(os.path.dirname(__file__), "output", "inventory")
os.makedirs(OUT_DIR, exist_ok=True)

random.seed(4004)
np.random.seed(4004)

REGION_CODES = [r[0] for r in REGIONS]

SKUS = [
    ("SKU-1001", "Widget Pro", "Widgets", 18.00),
    ("SKU-1002", "Widget Lite", "Widgets", 9.00),
    ("SKU-1003", "Gadget Max", "Gadgets", 55.00),
    ("SKU-1004", "Gadget Mini", "Gadgets", 32.00),
    ("SKU-1005", "Connector Kit", "Accessories", 4.50),
    ("SKU-1006", "Premium Bundle", "Bundles", 105.00),
    ("SKU-1007", "Starter Pack", "Bundles", 15.00),
    ("SKU-1008", "Enterprise License", "Digital", 200.00),
]


def gen_sku_master():
    rows = []
    for sku, name, category, cost in SKUS:
        rows.append({
            "sku": sku,
            "product_name": name,
            "category": category,
            "unit_cost": cost,
            "reorder_point": random.randint(50, 200),
        })
    return pd.DataFrame(rows)


def gen_stock_and_movements():
    stock_rows = []
    move_rows = []
    move_id = 1

    months = list(month_range(START_DATE, END_DATE))
    # running stock level per sku/region
    levels = {(sku, region): random.randint(300, 900) for sku, *_ in SKUS for region in REGION_CODES}

    for month in months:
        for sku, name, category, cost in SKUS:
            for region in REGION_CODES:
                key = (sku, region)
                start_level = levels[key]

                # digital goods don't move physical stock
                if category == "Digital":
                    stock_rows.append({
                        "sku": sku, "region_code": region, "month": month.isoformat(),
                        "quantity_on_hand": 0, "unit_cost": cost,
                    })
                    continue

                inbound = random.randint(80, 260)
                outbound = random.randint(70, 240)
                # seasonality bump for outbound in Nov/Dec, matching sales
                if month.month in (11, 12):
                    outbound = int(outbound * 1.3)

                end_level = max(0, start_level + inbound - outbound)
                levels[key] = end_level

                move_rows.append({
                    "movement_id": f"MOV-{move_id:07d}", "sku": sku, "region_code": region,
                    "month": month.isoformat(), "movement_type": "inbound", "quantity": inbound,
                })
                move_id += 1
                move_rows.append({
                    "movement_id": f"MOV-{move_id:07d}", "sku": sku, "region_code": region,
                    "month": month.isoformat(), "movement_type": "outbound", "quantity": outbound,
                })
                move_id += 1

                stock_rows.append({
                    "sku": sku, "region_code": region, "month": month.isoformat(),
                    "quantity_on_hand": end_level, "unit_cost": cost,
                })

    return pd.DataFrame(stock_rows), pd.DataFrame(move_rows)


def main():
    sku_df = gen_sku_master()
    stock_df, moves_df = gen_stock_and_movements()

    sku_df.to_csv(os.path.join(OUT_DIR, "sku_master.csv"), index=False)
    stock_df.to_csv(os.path.join(OUT_DIR, "stock_levels.csv"), index=False)
    moves_df.to_csv(os.path.join(OUT_DIR, "warehouse_movements.csv"), index=False)

    print(f"inventory: sku_master={len(sku_df)} stock_levels={len(stock_df)} warehouse_movements={len(moves_df)}")


if __name__ == "__main__":
    main()
