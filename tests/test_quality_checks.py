"""Unit tests for the cleaning/transform + data-quality-check functions
(catalog/quality_checks.py, catalog/transform.py::coerce_types)."""
import pandas as pd
import pytest

from schemas import DatasetSpec
from quality_checks import (
    check_nulls, check_duplicates, check_referential_integrity, dedupe, run_quality_checks,
)
from transform import coerce_types


SIMPLE_SPEC = DatasetSpec(
    domain="test", name="widgets",
    columns={"id": "string", "name": "string", "amount": "float", "qty": "int"},
    primary_key=["id"],
    not_null=["id", "name"],
)

CHILD_SPEC = DatasetSpec(
    domain="test", name="widget_orders",
    columns={"order_id": "string", "widget_id": "string"},
    primary_key=["order_id"],
    not_null=["order_id"],
    fk_checks=[("widget_id", "test.widgets", "id")],
)


def test_check_nulls_detects_missing_values():
    df = pd.DataFrame({"id": ["a", None, "c"], "name": ["x", "y", None]})
    violations = check_nulls(df, SIMPLE_SPEC)
    assert violations["id"] == 1
    assert violations["name"] == 1


def test_check_nulls_clean_data_has_no_violations():
    df = pd.DataFrame({"id": ["a", "b"], "name": ["x", "y"]})
    violations = check_nulls(df, SIMPLE_SPEC)
    assert violations["id"] == 0
    assert violations["name"] == 0


def test_check_duplicates_detects_repeated_primary_key():
    df = pd.DataFrame({"id": ["a", "a", "b"], "name": ["x", "x2", "y"]})
    assert check_duplicates(df, SIMPLE_SPEC) == 1


def test_dedupe_removes_duplicate_keys_keeping_last():
    df = pd.DataFrame({"id": ["a", "a", "b"], "name": ["old", "new", "y"]})
    result = dedupe(df, SIMPLE_SPEC)
    assert len(result) == 2
    assert result[result["id"] == "a"]["name"].iloc[0] == "new"


def test_referential_integrity_flags_orphaned_rows():
    parent = pd.DataFrame({"id": ["w1", "w2"]})
    child = pd.DataFrame({"order_id": ["o1", "o2"], "widget_id": ["w1", "w999"]})
    violations = check_referential_integrity(child, CHILD_SPEC, {"test.widgets": parent})
    assert violations["widget_id"] == 1


def test_referential_integrity_passes_when_all_keys_valid():
    parent = pd.DataFrame({"id": ["w1", "w2"]})
    child = pd.DataFrame({"order_id": ["o1", "o2"], "widget_id": ["w1", "w2"]})
    violations = check_referential_integrity(child, CHILD_SPEC, {"test.widgets": parent})
    assert violations["widget_id"] == 0


def test_run_quality_checks_passed_flag_true_for_clean_data():
    df = pd.DataFrame({"id": ["a", "b"], "name": ["x", "y"]})
    report = run_quality_checks(df, SIMPLE_SPEC)
    assert report.passed is True
    assert report.row_count == 2


def test_run_quality_checks_passed_flag_false_with_nulls():
    df = pd.DataFrame({"id": ["a", None], "name": ["x", "y"]})
    report = run_quality_checks(df, SIMPLE_SPEC)
    assert report.passed is False
    assert report.null_violations["id"] == 1


def test_coerce_types_converts_date_int_float_bool():
    spec = DatasetSpec(
        domain="test", name="mixed",
        columns={"d": "date", "n": "int", "f": "float", "b": "bool"},
        primary_key=["d"],
    )
    df = pd.DataFrame({
        "d": ["2024-01-15", "2024-02-01"],
        "n": ["10", "20"],
        "f": ["1.5", "2.75"],
        "b": ["true", "false"],
    })
    result = coerce_types(df, spec)
    assert str(result["d"].iloc[0]) == "2024-01-15"
    assert result["n"].iloc[0] == 10
    assert result["f"].iloc[1] == 2.75
    assert result["b"].iloc[0] == True
    assert result["b"].iloc[1] == False


def test_coerce_types_handles_bad_numeric_gracefully():
    spec = DatasetSpec(
        domain="test", name="mixed2",
        columns={"n": "int"}, primary_key=["n"],
    )
    df = pd.DataFrame({"n": ["10", "not_a_number"]})
    result = coerce_types(df, spec)
    assert result["n"].iloc[0] == 10
    assert pd.isna(result["n"].iloc[1])
