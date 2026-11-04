from __future__ import annotations
import argparse
from pathlib import Path
import json

from .market_data import download_latest_market_data,save_market_snapshot
from .research import run_daily_scan

def main():
    parser=argparse.ArgumentParser(description="ValueForge market refresh and daily research")
    parser.add_argument("command",choices=["refresh","scan","refresh-and-scan"])
    args=parser.parse_args()
    if args.command in ("refresh","refresh-and-scan"):
        frame,status=download_latest_market_data()
        save_market_snapshot(frame,status)
        print(f"Downloaded {len(frame):,} EOD rows. Dates: {status['exchange_dates']}")
    if args.command in ("scan","refresh-and-scan"):
        ranked,summary=run_daily_scan()
        print(json.dumps(summary,indent=2))
        print(ranked.head(20)[[c for c in ["exchange","symbol","name","close","ret_21d","value_score","research_status"] if c in ranked]].to_string(index=False))

if __name__=="__main__": main()
