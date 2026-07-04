"""Registry of pre-built cross-domain warehouse views, with metadata used
by both the LLM router and the deterministic fallback in analyze.py to
decide which view(s) answer a given natural-language question.
"""
from __future__ import annotations

REGISTERED_VIEWS = {
    "vw_revenue_vs_hr_cost": {
        "description": "Revenue, COGS, and gross margin vs HR cost, by department and month.",
        "keywords": ["hr cost", "headcount cost", "revenue", "margin", "department", "salary", "benefits"],
        "columns": ["department", "month_start", "hr_cost", "gl_revenue", "cogs", "gross_margin"],
    },
    "vw_revenue_vs_hr_cost_by_region": {
        "description": "Same as vw_revenue_vs_hr_cost but broken out by region as well as department.",
        "keywords": ["hr cost", "region", "revenue", "margin", "department"],
        "columns": ["department", "region_code", "month_start", "hr_cost", "gl_revenue", "cogs", "gross_margin"],
    },
    "vw_marketing_spend_vs_sales": {
        "description": "Marketing spend vs sales revenue and order count, by region and month.",
        "keywords": ["marketing", "spend", "campaign", "sales lift", "region", "channel"],
        "columns": ["region_code", "month_start", "marketing_spend", "sales_revenue", "order_count"],
    },
    "vw_inventory_turns_vs_sales": {
        "description": "Inventory turnover ratio (outbound qty / on-hand qty) vs sales velocity, by SKU/region/month.",
        "keywords": ["inventory", "turns", "turnover", "stock", "warehouse", "sku", "velocity"],
        "columns": ["sku", "region_code", "month_start", "quantity_on_hand", "outbound_qty", "turnover_ratio"],
    },
    "vw_department_pnl": {
        "description": "Department-level P&L: revenue, opex, budget, and HR cost by department/month.",
        "keywords": ["pnl", "p&l", "budget", "opex", "department", "profit", "loss"],
        "columns": ["department", "month_start", "revenue", "total_opex", "budget_amount", "hr_cost"],
    },
}
