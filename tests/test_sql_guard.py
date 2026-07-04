"""Unit tests for the read-only SQL safety guard (api/sql_guard.py)."""
import pytest

from sql_guard import validate_readonly_sql, UnsafeQueryError


def test_allows_simple_select():
    sql = "SELECT department, hr_cost FROM vw_revenue_vs_hr_cost"
    assert validate_readonly_sql(sql) == sql


def test_allows_select_with_trailing_semicolon():
    sql = "SELECT 1;"
    assert validate_readonly_sql(sql) == "SELECT 1"


def test_allows_cte_with_statement():
    sql = "WITH x AS (SELECT 1 AS a) SELECT a FROM x"
    assert validate_readonly_sql(sql) == sql


def test_rejects_insert():
    with pytest.raises(UnsafeQueryError):
        validate_readonly_sql("INSERT INTO foo VALUES (1)")


def test_rejects_drop_table():
    with pytest.raises(UnsafeQueryError):
        validate_readonly_sql("DROP TABLE fact_sales")


def test_rejects_delete():
    with pytest.raises(UnsafeQueryError):
        validate_readonly_sql("DELETE FROM fact_sales WHERE 1=1")


def test_rejects_update():
    with pytest.raises(UnsafeQueryError):
        validate_readonly_sql("UPDATE fact_sales SET order_total = 0")


def test_rejects_stacked_statements():
    with pytest.raises(UnsafeQueryError):
        validate_readonly_sql("SELECT 1; DROP TABLE fact_sales")


def test_rejects_non_select_start():
    with pytest.raises(UnsafeQueryError):
        validate_readonly_sql("EXPLAIN SELECT 1")


def test_rejects_empty_string():
    with pytest.raises(UnsafeQueryError):
        validate_readonly_sql("")


def test_rejects_information_schema_probe():
    with pytest.raises(UnsafeQueryError):
        validate_readonly_sql("SELECT * FROM information_schema.tables")


def test_rejects_pg_catalog_probe():
    with pytest.raises(UnsafeQueryError):
        validate_readonly_sql("SELECT * FROM pg_catalog.pg_tables")


def test_rejects_sql_comment_smuggling():
    with pytest.raises(UnsafeQueryError):
        validate_readonly_sql("SELECT 1 -- ; DROP TABLE fact_sales")


def test_rejects_select_into():
    with pytest.raises(UnsafeQueryError):
        validate_readonly_sql("SELECT * INTO new_table FROM fact_sales")


def test_rejects_pg_sleep_dos():
    with pytest.raises(UnsafeQueryError):
        validate_readonly_sql("SELECT pg_sleep(100)")
