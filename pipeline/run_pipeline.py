"""End-to-end pipeline runner: generate -> land-to-lake -> catalog/transform
-> warehouse-load, in order. Idempotent -- safe to re-run; each stage
overwrites/upserts rather than appending duplicate data.

Usage:
    python pipeline/run_pipeline.py [--skip-generate]
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_step(name: str, cmd: list[str], cwd: str):
    print(f"\n{'=' * 60}\nSTEP: {name}\n{'=' * 60}")
    start = time.time()
    result = subprocess.run(cmd, cwd=cwd)
    elapsed = time.time() - start
    if result.returncode != 0:
        print(f"[FAILED] {name} exited with code {result.returncode} after {elapsed:.1f}s")
        sys.exit(result.returncode)
    print(f"[OK] {name} completed in {elapsed:.1f}s")


def main():
    parser = argparse.ArgumentParser(description="Run the full data lake pipeline.")
    parser.add_argument("--skip-generate", action="store_true", help="skip synthetic data generation")
    args = parser.parse_args()

    python = sys.executable

    if not args.skip_generate:
        run_step("generate synthetic domain data", [python, "run_all.py"], cwd=os.path.join(ROOT, "generators"))

    run_step("land raw data to lake (MinIO)", [python, "land_to_lake.py"], cwd=os.path.join(ROOT, "lake", "ingest"))
    run_step("catalog + transform (Glue-equivalent)", [python, "transform.py"], cwd=os.path.join(ROOT, "catalog"))
    run_step("load warehouse (Postgres star schema)", [python, "load_warehouse.py"], cwd=os.path.join(ROOT, "warehouse"))
    run_step("export Power BI CSVs", [python, "export_powerbi.py"], cwd=os.path.join(ROOT, "dashboard"))

    print("\nPipeline complete. Warehouse is ready to query via the API and dashboard.")


if __name__ == "__main__":
    main()
