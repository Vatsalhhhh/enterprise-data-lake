"""Read-only SQL safety guard used before any LLM-generated (or template
-generated) SQL is executed against the warehouse.

Rules enforced:
  - must be a single statement
  - must start with SELECT or WITH (a CTE feeding a SELECT)
  - no DDL/DML keywords anywhere in the statement
  - no semicolon-separated statement stacking
  - no access to information_schema / pg_catalog (blocks metadata probing)
"""
from __future__ import annotations

import re

FORBIDDEN_KEYWORDS = [
    "insert", "update", "delete", "drop", "alter", "truncate", "grant",
    "revoke", "create", "replace", "merge", "call", "execute", "copy",
    "vacuum", "reindex", "comment", "security", "attach", "detach",
    "pg_sleep", "dblink", "into",
]

FORBIDDEN_SCHEMAS = ["information_schema", "pg_catalog", "pg_"]


class UnsafeQueryError(ValueError):
    pass


def validate_readonly_sql(sql: str) -> str:
    """Raises UnsafeQueryError if the SQL is not a safe, single, read-only
    SELECT/CTE statement. Returns the trimmed statement on success."""
    if not sql or not sql.strip():
        raise UnsafeQueryError("empty SQL")

    cleaned = sql.strip()

    # strip a single trailing semicolon, then reject if any semicolon remains
    if cleaned.endswith(";"):
        cleaned = cleaned[:-1].strip()
    if ";" in cleaned:
        raise UnsafeQueryError("multiple statements are not allowed")

    lowered = cleaned.lower()

    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise UnsafeQueryError("only SELECT/CTE read queries are allowed")

    # word-boundary scan for forbidden keywords so we don't false-positive
    # on substrings like "createdat" while still catching "create table"
    tokens = re.findall(r"[a-zA-Z_]+", lowered)
    token_set = set(tokens)
    for kw in FORBIDDEN_KEYWORDS:
        if kw in token_set:
            raise UnsafeQueryError(f"forbidden keyword detected: {kw}")

    for schema in FORBIDDEN_SCHEMAS:
        if schema in lowered:
            raise UnsafeQueryError(f"access to '{schema}' is not allowed")

    # comments can be used to smuggle statements past naive checks
    if "--" in cleaned or "/*" in cleaned:
        raise UnsafeQueryError("SQL comments are not allowed")

    return cleaned
