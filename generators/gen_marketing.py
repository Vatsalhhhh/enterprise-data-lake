"""Generates synthetic Marketing domain CSVs: campaigns, spend_by_channel, leads_by_campaign."""
from __future__ import annotations

import os
import random
import datetime as dt

import numpy as np
import pandas as pd

from common import START_DATE, END_DATE, REGIONS, month_range

OUT_DIR = os.path.join(os.path.dirname(__file__), "output", "marketing")
os.makedirs(OUT_DIR, exist_ok=True)

random.seed(5005)
np.random.seed(5005)

REGION_CODES = [r[0] for r in REGIONS]
CHANNELS = ["Paid Search", "Social", "Email", "Events", "Content/SEO", "Partnerships"]


def gen_campaigns():
    rows = []
    cid = 1
    months = list(month_range(START_DATE, END_DATE))
    for month in months:
        n_campaigns = random.randint(2, 5)
        for _ in range(n_campaigns):
            region = random.choice(REGION_CODES)
            channel = random.choice(CHANNELS)
            duration_days = random.randint(14, 45)
            start = dt.date(month.year, month.month, random.randint(1, 5))
            end = start + dt.timedelta(days=duration_days)
            rows.append({
                "campaign_id": f"CMP-{cid:05d}",
                "name": f"{channel} Push {month.strftime('%b %Y')} #{cid}",
                "channel": channel,
                "region_code": region,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
            })
            cid += 1
    return pd.DataFrame(rows)


def gen_spend_and_leads(campaigns: pd.DataFrame):
    spend_rows = []
    lead_rows = []
    lead_id = 1

    for _, camp in campaigns.iterrows():
        month = dt.date.fromisoformat(camp["start_date"]).replace(day=1)
        base_spend = {
            "Paid Search": 18000, "Social": 12000, "Email": 3000,
            "Events": 35000, "Content/SEO": 8000, "Partnerships": 15000,
        }[camp["channel"]]
        spend = base_spend * np.random.uniform(0.7, 1.4)

        spend_rows.append({
            "campaign_id": camp["campaign_id"],
            "channel": camp["channel"],
            "region_code": camp["region_code"],
            "month": month.isoformat(),
            "spend_amount": round(spend, 2),
        })

        # leads generated roughly proportional to spend with channel efficiency
        efficiency = {
            "Paid Search": 0.018, "Social": 0.015, "Email": 0.05,
            "Events": 0.006, "Content/SEO": 0.02, "Partnerships": 0.01,
        }[camp["channel"]]
        n_leads = max(1, int(spend * efficiency * np.random.uniform(0.7, 1.3)))

        for _ in range(n_leads):
            converted = random.random() < np.random.uniform(0.08, 0.22)
            lead_rows.append({
                "lead_id": f"LEAD-{lead_id:07d}",
                "campaign_id": camp["campaign_id"],
                "region_code": camp["region_code"],
                "month": month.isoformat(),
                "converted": converted,
            })
            lead_id += 1

    return pd.DataFrame(spend_rows), pd.DataFrame(lead_rows)


def main():
    campaigns_df = gen_campaigns()
    spend_df, leads_df = gen_spend_and_leads(campaigns_df)

    campaigns_df.to_csv(os.path.join(OUT_DIR, "campaigns.csv"), index=False)
    spend_df.to_csv(os.path.join(OUT_DIR, "spend_by_channel.csv"), index=False)
    leads_df.to_csv(os.path.join(OUT_DIR, "leads_by_campaign.csv"), index=False)

    print(f"marketing: campaigns={len(campaigns_df)} spend_by_channel={len(spend_df)} leads_by_campaign={len(leads_df)}")


if __name__ == "__main__":
    main()
