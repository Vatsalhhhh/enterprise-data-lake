"""Runs every domain generator in sequence and reports row counts.

Usage: python generators/run_all.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import gen_sales
import gen_hr
import gen_finance
import gen_inventory
import gen_marketing


def main():
    print("Generating synthetic domain data...")
    gen_sales.main()
    gen_hr.main()
    gen_finance.main()
    gen_inventory.main()
    gen_marketing.main()
    print("Done. CSVs written under generators/output/<domain>/")


if __name__ == "__main__":
    main()
