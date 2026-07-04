"""Tests for the deterministic offline fallback path in api/analyze.py.

These exercise view selection (pure, no DB needed) and, when a live
Postgres warehouse is reachable, the actual query + narration path.
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "")  # force fallback mode for these tests

from analyze import pick_views, analyze_fallback, analyze


def test_pick_views_matches_hr_keywords():
    views = pick_views("Compare HR costs with revenue")
    assert "vw_revenue_vs_hr_cost" in views


def test_pick_views_matches_marketing_keywords():
    views = pick_views("How does marketing spend compare to sales in each region?")
    assert views[0] == "vw_marketing_spend_vs_sales"


def test_pick_views_matches_inventory_keywords():
    views = pick_views("What is our inventory turnover vs sales velocity?")
    assert views[0] == "vw_inventory_turns_vs_sales"


def test_pick_views_defaults_when_no_keywords_match():
    views = pick_views("asdkjhaskjdh random gibberish query")
    assert len(views) == 1


@pytest.mark.requires_pg
def test_analyze_fallback_returns_grounded_answer_with_real_numbers():
    result = analyze_fallback("Compare HR costs with revenue")
    assert result.mode == "fallback"
    assert "vw_revenue_vs_hr_cost" in result.views_used
    assert len(result.data_preview) > 0
    assert "$" in result.answer  # cites real dollar figures
    # the answer should mention at least one department name from the data
    assert any(row["department"] in result.answer for row in result.data_preview)


@pytest.mark.requires_pg
def test_analyze_top_level_uses_fallback_when_no_api_key():
    result = analyze("Compare marketing spend vs sales by region")
    assert result.mode == "fallback"
    assert result.sql.lower().startswith("select")


@pytest.mark.requires_pg
def test_analyze_fallback_sql_is_readonly():
    from sql_guard import validate_readonly_sql
    result = analyze_fallback("department pnl and budget variance")
    # should not raise
    validate_readonly_sql(result.sql)


@pytest.mark.requires_pg
def test_analyze_fallback_data_preview_is_json_serializable():
    """Regression test: some SKUs have zero stock on hand throughout the
    period, so AVG(turnover_ratio) is SQL NULL for them, which pandas reads
    as NaN. df.where(pd.notna(df), None) doesn't reliably clear that on a
    float64 column, and standard JSON has no NaN literal -- Starlette's
    JSONResponse (allow_nan=False) used to 500 on this exact question."""
    import json
    import math

    result = analyze_fallback("What is our inventory turnover?")
    assert result.views_used == ["vw_inventory_turns_vs_sales"]

    # json.dumps with allow_nan=False matches Starlette's actual behavior,
    # unlike the default allow_nan=True which would mask this bug.
    json.dumps(result.data_preview, allow_nan=False)

    for row in result.data_preview:
        for value in row.values():
            if isinstance(value, float):
                assert not math.isnan(value)
