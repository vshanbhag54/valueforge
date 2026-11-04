from __future__ import annotations
from pathlib import Path
import json
import pandas as pd

from .fundamentals import latest_fundamentals, normalize_fundamentals
from .market_data import load_market_snapshot
from .scoring import screen_universe

FUNDAMENTALS_PATH=Path("data/fundamentals/company_fundamentals.csv")

def load_fundamentals(path=FUNDAMENTALS_PATH):
    p=Path(path)
    if not p.exists(): return pd.DataFrame()
    raw=pd.read_csv(p)
    # Already-normalized data is also accepted.
    return latest_fundamentals(normalize_fundamentals(raw,source_label="Repository fundamentals file"))

def merge_market_and_fundamentals(market,fundamentals):
    base=market.copy()
    if fundamentals.empty:
        base["source_label"]="Market data only"
        return base
    f=latest_fundamentals(fundamentals)
    # Prefer stable ISIN mapping; ticker matching is a fallback only when ISIN is absent.
    for field in f.columns:
        if field in {"isin","symbol","name","exchange"}: continue
        values={}
        if "isin" in f and "isin" in base:
            part=f.dropna(subset=["isin"]).drop_duplicates("isin",keep="last")
            values=part.set_index("isin")[field].to_dict()
            mapped=base["isin"].map(values)
        else:
            mapped=pd.Series(index=base.index,dtype=object)
        if "symbol" in f and "symbol" in base:
            part=f.dropna(subset=["symbol"]).drop_duplicates("symbol",keep="last")
            by_symbol=part.set_index("symbol")[field].to_dict()
            fallback=base["symbol"].astype(str).str.upper().map(by_symbol)
            mapped=mapped.where(mapped.notna(),fallback)
        if field not in base: base[field]=mapped
        else: base[field]=base[field].where(base[field].notna(),mapped)
    base["fundamentals_match"] = base.get("pe",pd.Series(index=base.index,dtype=float)).notna()
    return base

def run_daily_scan(market_path="data/live/market_latest.csv",fundamentals_path=FUNDAMENTALS_PATH,output_dir="data/live"):
    market=load_market_snapshot(market_path)
    if market.empty: raise RuntimeError("No market snapshot found. Run the market refresh workflow first.")
    fundamentals=load_fundamentals(fundamentals_path)
    merged=merge_market_and_fundamentals(market,fundamentals)
    result=screen_universe(merged)
    out=Path(output_dir); out.mkdir(parents=True,exist_ok=True)
    ranked=result.companies.sort_values(["value_score","volume"],ascending=[False,False],na_position="last")
    ranked.to_csv(out/"daily_research.csv",index=False)
    summary={
      "scan_at_utc":pd.Timestamp.now(tz="UTC").isoformat(),
      "market_rows":int(len(market)),
      "fundamental_rows":int(len(fundamentals)),
      "matched_rows":int(merged.get("fundamentals_match",pd.Series(dtype=bool)).sum()),
      "market_date":str(market["snapshot_date"].max()) if "snapshot_date" in market else "unknown",
      **result.summary,
      "method":"Deterministic value/quality triage; no broker actions."
    }
    (out/"research_status.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    return ranked,summary
