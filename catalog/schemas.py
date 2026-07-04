"""Expected schemas and data-quality rules for each raw dataset.

This is the substitute for a Glue Data Catalog table definition: for each
dataset we know the expected columns/dtypes, the primary/partition keys,
and a handful of quality checks to apply during the transform step.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DatasetSpec:
    domain: str
    name: str
    columns: dict  # column -> pandas dtype string
    primary_key: list
    not_null: list = field(default_factory=list)
    fk_checks: list = field(default_factory=list)  # list of (column, referenced_dataset, referenced_column)


DATASET_SPECS = {
    # --- sales ---
    "sales.regions": DatasetSpec(
        domain="sales", name="regions",
        columns={"region_code": "string", "country_group": "string", "sub_region": "string"},
        primary_key=["region_code"],
        not_null=["region_code"],
    ),
    "sales.customers": DatasetSpec(
        domain="sales", name="customers",
        columns={"customer_id": "string", "region_code": "string", "segment": "string", "signup_date": "date"},
        primary_key=["customer_id"],
        not_null=["customer_id", "region_code"],
        fk_checks=[("region_code", "sales.regions", "region_code")],
    ),
    "sales.orders": DatasetSpec(
        domain="sales", name="orders",
        columns={"order_id": "string", "customer_id": "string", "region_code": "string", "order_date": "date",
                 "order_total": "float", "order_cost": "float", "status": "string"},
        primary_key=["order_id"],
        not_null=["order_id", "customer_id", "order_date"],
        fk_checks=[("customer_id", "sales.customers", "customer_id")],
    ),
    "sales.order_lines": DatasetSpec(
        domain="sales", name="order_lines",
        columns={"order_line_id": "string", "order_id": "string", "sku": "string", "product_name": "string",
                 "quantity": "int", "unit_price": "float", "unit_cost": "float",
                 "discount_rate": "float", "line_net_amount": "float"},
        primary_key=["order_line_id"],
        not_null=["order_line_id", "order_id", "sku"],
        fk_checks=[("order_id", "sales.orders", "order_id")],
    ),
    # --- hr ---
    "hr.employees": DatasetSpec(
        domain="hr", name="employees",
        columns={"employee_id": "string", "department": "string", "region_code": "string",
                 "hire_date": "date", "job_level": "string"},
        primary_key=["employee_id"],
        not_null=["employee_id", "department", "region_code"],
    ),
    "hr.headcount_costs": DatasetSpec(
        domain="hr", name="headcount_costs",
        columns={"department": "string", "region_code": "string", "month": "date", "headcount": "int",
                 "salary_cost": "float", "benefits_cost": "float", "total_cost": "float"},
        primary_key=["department", "region_code", "month"],
        not_null=["department", "region_code", "month"],
    ),
    "hr.attrition_events": DatasetSpec(
        domain="hr", name="attrition_events",
        columns={"event_id": "string", "employee_id": "string", "department": "string",
                 "region_code": "string", "termination_date": "date", "reason": "string"},
        primary_key=["event_id"],
        not_null=["event_id", "employee_id"],
        fk_checks=[("employee_id", "hr.employees", "employee_id")],
    ),
    # --- finance ---
    "finance.budgets_by_department": DatasetSpec(
        domain="finance", name="budgets_by_department",
        columns={"department": "string", "month": "date", "budget_amount": "float"},
        primary_key=["department", "month"],
        not_null=["department", "month"],
    ),
    "finance.revenue_by_month": DatasetSpec(
        domain="finance", name="revenue_by_month",
        columns={"region_code": "string", "month": "date", "revenue": "float"},
        primary_key=["region_code", "month"],
        not_null=["region_code", "month"],
    ),
    "finance.gl_transactions": DatasetSpec(
        domain="finance", name="gl_transactions",
        columns={"txn_id": "string", "department": "string", "region_code": "string", "month": "date",
                 "account_code": "string", "account_name": "string", "amount": "float"},
        primary_key=["txn_id"],
        not_null=["txn_id", "department", "month", "account_code"],
    ),
    # --- inventory ---
    "inventory.sku_master": DatasetSpec(
        domain="inventory", name="sku_master",
        columns={"sku": "string", "product_name": "string", "category": "string",
                 "unit_cost": "float", "reorder_point": "int"},
        primary_key=["sku"],
        not_null=["sku"],
    ),
    "inventory.stock_levels": DatasetSpec(
        domain="inventory", name="stock_levels",
        columns={"sku": "string", "region_code": "string", "month": "date",
                 "quantity_on_hand": "int", "unit_cost": "float"},
        primary_key=["sku", "region_code", "month"],
        not_null=["sku", "region_code", "month"],
        fk_checks=[("sku", "inventory.sku_master", "sku")],
    ),
    "inventory.warehouse_movements": DatasetSpec(
        domain="inventory", name="warehouse_movements",
        columns={"movement_id": "string", "sku": "string", "region_code": "string", "month": "date",
                 "movement_type": "string", "quantity": "int"},
        primary_key=["movement_id"],
        not_null=["movement_id", "sku"],
        fk_checks=[("sku", "inventory.sku_master", "sku")],
    ),
    # --- marketing ---
    "marketing.campaigns": DatasetSpec(
        domain="marketing", name="campaigns",
        columns={"campaign_id": "string", "name": "string", "channel": "string",
                 "region_code": "string", "start_date": "date", "end_date": "date"},
        primary_key=["campaign_id"],
        not_null=["campaign_id", "channel"],
    ),
    "marketing.spend_by_channel": DatasetSpec(
        domain="marketing", name="spend_by_channel",
        columns={"campaign_id": "string", "channel": "string", "region_code": "string",
                 "month": "date", "spend_amount": "float"},
        primary_key=["campaign_id"],
        not_null=["campaign_id", "channel", "month"],
        fk_checks=[("campaign_id", "marketing.campaigns", "campaign_id")],
    ),
    "marketing.leads_by_campaign": DatasetSpec(
        domain="marketing", name="leads_by_campaign",
        columns={"lead_id": "string", "campaign_id": "string", "region_code": "string",
                 "month": "date", "converted": "bool"},
        primary_key=["lead_id"],
        not_null=["lead_id", "campaign_id"],
        fk_checks=[("campaign_id", "marketing.campaigns", "campaign_id")],
    ),
}


def get_spec(domain: str, name: str) -> DatasetSpec:
    return DATASET_SPECS[f"{domain}.{name}"]
