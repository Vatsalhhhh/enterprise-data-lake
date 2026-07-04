"""Data-quality checks applied to each dataset during the transform step.

Mirrors the kind of checks a Glue ETL job or a dbt test suite would run:
null checks on required columns, referential-integrity checks against
already-transformed parent datasets, and duplicate-key detection.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from schemas import DatasetSpec


@dataclass
class QualityReport:
    dataset: str
    row_count: int
    null_violations: dict = field(default_factory=dict)
    duplicate_key_count: int = 0
    fk_violations: dict = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return (
            all(v == 0 for v in self.null_violations.values())
            and self.duplicate_key_count == 0
            and all(v == 0 for v in self.fk_violations.values())
        )

    def as_dict(self):
        return {
            "dataset": self.dataset,
            "row_count": self.row_count,
            "null_violations": self.null_violations,
            "duplicate_key_count": self.duplicate_key_count,
            "fk_violations": self.fk_violations,
            "passed": self.passed,
        }


def check_nulls(df: pd.DataFrame, spec: DatasetSpec) -> dict:
    violations = {}
    for col in spec.not_null:
        if col in df.columns:
            violations[col] = int(df[col].isna().sum())
    return violations


def check_duplicates(df: pd.DataFrame, spec: DatasetSpec) -> int:
    if not spec.primary_key:
        return 0
    key_cols = [c for c in spec.primary_key if c in df.columns]
    if not key_cols:
        return 0
    return int(df.duplicated(subset=key_cols).sum())


def check_referential_integrity(df: pd.DataFrame, spec: DatasetSpec, parent_frames: dict) -> dict:
    """parent_frames maps 'domain.dataset' -> DataFrame of already-cleaned parents."""
    violations = {}
    for col, ref_dataset, ref_col in spec.fk_checks:
        parent = parent_frames.get(ref_dataset)
        if parent is None or col not in df.columns:
            violations[col] = -1  # parent unavailable, cannot verify
            continue
        valid_values = set(parent[ref_col].dropna().unique())
        orphaned = df[~df[col].isin(valid_values) & df[col].notna()]
        violations[col] = int(len(orphaned))
    return violations


def dedupe(df: pd.DataFrame, spec: DatasetSpec) -> pd.DataFrame:
    key_cols = [c for c in spec.primary_key if c in df.columns]
    if not key_cols:
        return df
    return df.drop_duplicates(subset=key_cols, keep="last").reset_index(drop=True)


def run_quality_checks(df: pd.DataFrame, spec: DatasetSpec, parent_frames: dict | None = None) -> QualityReport:
    parent_frames = parent_frames or {}
    report = QualityReport(dataset=f"{spec.domain}.{spec.name}", row_count=len(df))
    report.null_violations = check_nulls(df, spec)
    report.duplicate_key_count = check_duplicates(df, spec)
    report.fk_violations = check_referential_integrity(df, spec, parent_frames)
    return report
