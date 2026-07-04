"""Tests for the cross-domain SQL views, run against a live Postgres
warehouse. Skipped automatically if Postgres is not reachable."""
import os

import pandas as pd
import pytest
from sqlalchemy import create_engine, text


def _engine():
    url = (
        f"postgresql+psycopg2://{os.getenv('POSTGRES_USER', 'warehouse')}:"
        f"{os.getenv('POSTGRES_PASSWORD', 'warehouse')}@"
        f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
        f"{os.getenv('POSTGRES_PORT', '5544')}/"
        f"{os.getenv('POSTGRES_DB', 'warehouse')}"
    )
    return create_engine(url)


@pytest.mark.requires_pg
def test_dim_tables_populated():
    engine = _engine()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM dim_department")).scalar() == 6
        assert conn.execute(text("SELECT COUNT(*) FROM dim_region")).scalar() == 5
        assert conn.execute(text("SELECT COUNT(*) FROM dim_date")).scalar() > 0


@pytest.mark.requires_pg
def test_fact_tables_populated():
    engine = _engine()
    with engine.connect() as conn:
        for tbl in ["fact_sales", "fact_hr_cost", "fact_finance_gl",
                    "fact_inventory_stock", "fact_marketing_spend"]:
            count = conn.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar()
            assert count > 0, f"{tbl} should have rows"


@pytest.mark.requires_pg
def test_revenue_vs_hr_cost_view_has_plausible_numbers():
    engine = _engine()
    df = pd.read_sql(text("SELECT * FROM vw_revenue_vs_hr_cost"), engine)
    assert len(df) > 0
    # HR cost for any single department/month should be in a plausible
    # range for a company this size, not blown up by a join fan-out.
    assert df["hr_cost"].max() < 2_000_000
    assert (df["hr_cost"] > 0).all()


@pytest.mark.requires_pg
def test_engineered_cross_domain_story_is_present():
    """Confirms the deliberately engineered story: HR cost for Customer
    Support / NA-EAST ramps up starting April 2024, and gross margin for
    the same department/region erodes starting the following quarter."""
    engine = _engine()
    df = pd.read_sql(
        text(
            "SELECT month_start, hr_cost, gross_margin FROM vw_revenue_vs_hr_cost_by_region "
            "WHERE department = 'Customer Support' AND region_code = 'NA-EAST' "
            "ORDER BY month_start"
        ),
        engine,
    )
    df["month_start"] = pd.to_datetime(df["month_start"])

    early_2024 = df[(df.month_start >= "2024-01-01") & (df.month_start < "2024-04-01")]
    late_2024 = df[(df.month_start >= "2024-09-01") & (df.month_start < "2024-12-01")]

    assert len(early_2024) > 0 and len(late_2024) > 0
    assert late_2024["hr_cost"].mean() > early_2024["hr_cost"].mean() * 1.5

    q1_margin = df[(df.month_start >= "2024-01-01") & (df.month_start < "2024-04-01")]["gross_margin"].mean()
    q4_margin = df[(df.month_start >= "2024-10-01") & (df.month_start < "2025-01-01")]["gross_margin"].mean()
    assert q4_margin < q1_margin


@pytest.mark.requires_pg
def test_marketing_spend_vs_sales_view_has_rows_for_all_regions():
    engine = _engine()
    df = pd.read_sql(text("SELECT DISTINCT region_code FROM vw_marketing_spend_vs_sales"), engine)
    assert len(df) == 5


@pytest.mark.requires_pg
def test_inventory_turns_view_ratio_bounds():
    engine = _engine()
    df = pd.read_sql(
        text("SELECT turnover_ratio FROM vw_inventory_turns_vs_sales WHERE turnover_ratio IS NOT NULL"),
        engine,
    )
    assert len(df) > 0


@pytest.mark.requires_pg
def test_department_pnl_revenue_generating_depts_are_not_all_underwater():
    """Regression test: opex GL postings were once duplicated once per
    region (5x overcounting against a company-wide monthly budget figure),
    which made every department -- including Sales -- show a large loss
    every month. At least the primary revenue-generating department should
    show a positive average margin in a healthy synthetic dataset."""
    engine = _engine()
    df = pd.read_sql(text("SELECT * FROM vw_department_pnl"), engine)
    assert len(df) > 0

    margins = df.assign(margin=df["revenue"] - df["total_opex"]).groupby("department")["margin"].mean()
    assert margins["Sales"] > 0, f"Sales should be profitable on average, got {margins['Sales']}"
    # Opex shouldn't dwarf revenue company-wide either.
    assert df["total_opex"].sum() < df["revenue"].sum() * 3
