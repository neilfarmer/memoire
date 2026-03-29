"""AWS Cost Explorer helpers.

Cost Explorer is a global service — the boto3 client always targets us-east-1
regardless of where the Lambda is deployed.

Tag filtering requires "Cost allocation tags" to be activated in the AWS Billing
console under Cost allocation tags → activate the "Project" tag.
Costs have an ~24 h delay, so "last day" shows yesterday's spend.
"""

import os
import boto3
from datetime import date, timedelta
from response import ok, server_error

PROJECT_TAG = os.environ.get("PROJECT_NAME", "memoire")

# CE is always accessed via the us-east-1 endpoint
_ce = boto3.client("ce", region_name="us-east-1")


def _tag_filter():
    return {
        "Tags": {
            "Key": "Project",
            "Values": [PROJECT_TAG],
        }
    }


def get_costs():
    today      = date.today()
    # CE end date is exclusive; most recent complete day is yesterday
    end_date   = today.isoformat()
    start_date = (today - timedelta(days=30)).isoformat()

    try:
        resp = _ce.get_cost_and_usage(
            TimePeriod={"Start": start_date, "End": end_date},
            Granularity="DAILY",
            Filter=_tag_filter(),
            Metrics=["UnblendedCost"],
        )
    except Exception as e:
        return server_error(f"Cost Explorer error: {e}")

    daily = []
    for r in resp.get("ResultsByTime", []):
        amount = float(r["Total"]["UnblendedCost"]["Amount"])
        daily.append({
            "date":   r["TimePeriod"]["Start"],
            "amount": round(amount, 4),
        })

    # Aggregate windows (CE end is exclusive so last entry = yesterday)
    last_day   = round(daily[-1]["amount"], 4)   if daily           else 0.0
    last_week  = round(sum(d["amount"] for d in daily[-7:]),  4) if daily else 0.0
    last_month = round(sum(d["amount"] for d in daily),       4)

    return ok({
        "last_day":   last_day,
        "last_week":  last_week,
        "last_month": last_month,
        "daily":      daily,
        "currency":   "USD",
    })
