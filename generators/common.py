"""Shared constants and helpers used by every domain generator.

All five generators (sales, hr, finance, inventory, marketing) are built
around the same three-year timeline and the same department/region
dimensions so that the resulting facts can be joined cleanly once they
reach the warehouse. The one deliberately engineered story in the data is
described in `STORY` below -- it's what the cross-domain analysis in the
API/dashboard is meant to surface.
"""
from __future__ import annotations

import datetime as dt
import random

import numpy as np

SEED = 20220101
random.seed(SEED)
np.random.seed(SEED)

START_DATE = dt.date(2023, 1, 1)
END_DATE = dt.date(2025, 12, 31)

DEPARTMENTS = [
    "Sales",
    "Engineering",
    "Marketing",
    "Customer Support",
    "Operations",
    "Finance",
]

REGIONS = [
    ("NA-EAST", "North America", "East"),
    ("NA-WEST", "North America", "West"),
    ("EU-CENTRAL", "Europe", "Central"),
    ("APAC-SE", "Asia Pacific", "Southeast"),
    ("LATAM", "Latin America", "All"),
]

REGION_CODES = [r[0] for r in REGIONS]

# The engineered cross-domain story:
# Customer Support headcount cost climbs steadily through 2024 (extra hires
# + overtime/benefits) in the NA-EAST region's supporting cost center, while
# in Q3-Q4 2024 gross margin in Finance for the same department/region
# combination erodes noticeably faster than the rest of the business. This
# gives the analyst something concrete to discover: rising HR cost in one
# department preceded a margin squeeze in the following quarter, and it
# lines up with a spike in support-related order refunds/discounts.
STORY_DEPARTMENT = "Customer Support"
STORY_REGION = "NA-EAST"
STORY_START = dt.date(2024, 4, 1)   # HR cost inflation begins
STORY_MARGIN_HIT = dt.date(2024, 7, 1)  # margin erosion begins (one quarter later)


def month_range(start: dt.date, end: dt.date):
    """Yield the first day of each month between start and end inclusive."""
    cur = dt.date(start.year, start.month, 1)
    while cur <= end:
        yield cur
        if cur.month == 12:
            cur = dt.date(cur.year + 1, 1, 1)
        else:
            cur = dt.date(cur.year, cur.month + 1, 1)


def daterange(start: dt.date, end: dt.date):
    for n in range((end - start).days + 1):
        yield start + dt.timedelta(days=n)


def is_story_window(dept: str, region: str, month: dt.date) -> bool:
    return dept == STORY_DEPARTMENT and region == STORY_REGION and month >= STORY_START
