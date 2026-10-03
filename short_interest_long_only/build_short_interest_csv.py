"""
Build short_interest.csv for the QuantConnect algorithm from FINRA's public
Consolidated Short Interest dataset (https://api.finra.org).

Run locally (not inside QuantConnect):
    pip install requests
    python build_short_interest_csv.py --start 2015-01-01 --out short_interest.csv

Then upload short_interest.csv to your QuantConnect Object Store
(Organization > Object Store, or `lean cloud object-store set`), or host it
somewhere and pass the URL as the `short_interest_url` parameter.

Output columns: date,ticker,short_interest,avg_daily_volume
"""
import argparse
import csv
import requests

URL = "https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest"
PAGE = 5000


def fetch(start, end):
    offset = 0
    while True:
        body = {
            "limit": PAGE,
            "offset": offset,
            "fields": [
                "settlementDate",
                "symbolCode",
                "currentShortPositionQuantity",
                "averageDailyVolumeQuantity",
            ],
            "dateRangeFilters": [
                {"fieldName": "settlementDate", "startDate": start, "endDate": end}
            ],
        }
        resp = requests.post(URL, json=body, headers={"Accept": "application/json"}, timeout=60)
        resp.raise_for_status()
        rows = resp.json() if resp.text.strip() else []
        if not rows:
            return
        yield from rows
        if len(rows) < PAGE:
            return
        offset += PAGE


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default="2099-12-31")
    parser.add_argument("--out", default="short_interest.csv")
    args = parser.parse_args()

    count = 0
    with open(args.out, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["date", "ticker", "short_interest", "avg_daily_volume"])
        for r in fetch(args.start, args.end):
            if not r.get("symbolCode") or r.get("currentShortPositionQuantity") is None:
                continue
            writer.writerow([
                r["settlementDate"],
                r["symbolCode"],
                r["currentShortPositionQuantity"],
                r.get("averageDailyVolumeQuantity") or "",
            ])
            count += 1
    print(f"wrote {count} rows to {args.out}")


if __name__ == "__main__":
    main()
