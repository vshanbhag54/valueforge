from __future__ import annotations
import argparse
import json
from datetime import date
from pathlib import Path

from .market_data import download_latest_market_data,save_market_snapshot
from .research import run_daily_scan
from .filings import sync_xbrl_filings


def main():
    parser=argparse.ArgumentParser(description="ValueForge live EOD market and XBRL research operation")
    parser.add_argument("command",choices=["refresh","scan","refresh-and-scan","sync-filings"])
    parser.add_argument("--lookback-days",type=int,default=45,help="Filing discovery lookback; use 1825 for an initial five-year queue.")
    parser.add_argument("--limit",type=int,default=60,help="Maximum XBRL documents parsed in this run.")
    parser.add_argument("--workers",type=int,default=4,help="Polite concurrent filing downloads (max 6).")
    args=parser.parse_args()
    if args.command=="sync-filings":
        status=sync_xbrl_filings(args.lookback_days,args.limit,args.workers)
        print(json.dumps(status,indent=2))
        return
    if args.command in ("refresh","refresh-and-scan"):
        frame,status=download_latest_market_data()
        save_market_snapshot(frame,status)
        print(f"Downloaded {len(frame):,} EOD rows. Dates: {status['exchange_dates']}")
    if args.command in ("scan","refresh-and-scan"):
        ranked,summary=run_daily_scan()
        print(json.dumps(summary,indent=2))
        cols=[c for c in ["exchange","symbol","name","close","ret_21d","pe","roe","value_score","research_status"] if c in ranked]
        print(ranked.head(20)[cols].to_string(index=False))


if __name__=="__main__":
    main()
