from __future__ import annotations
from pathlib import Path
import json, os, re
import pandas as pd

from .fundamentals import latest_fundamentals, normalize_fundamentals
from .market_data import load_market_snapshot
from .scoring import screen_universe

FUNDAMENTALS_PATH=Path("data/fundamentals/company_fundamentals.csv")

def load_fundamentals(path=FUNDAMENTALS_PATH):
    p=Path(path)
    if not p.exists(): return pd.DataFrame()
    return latest_fundamentals(normalize_fundamentals(pd.read_csv(p),source_label="Repository fundamentals file"))

def merge_market_and_fundamentals(market,fundamentals):
    base=market.copy()
    if fundamentals.empty:
        base["source_label"]="Market data only"
        return base
    f=latest_fundamentals(fundamentals)
    # ISIN is the stable cross-exchange key; symbol matching is fallback only.
    for field in f.columns:
        if field in {"isin","symbol","name","exchange"}: continue
        mapped=pd.Series(index=base.index,dtype=object)
        if "isin" in f and "isin" in base:
            part=f.dropna(subset=["isin"]).drop_duplicates("isin",keep="last")
            mapped=base["isin"].map(part.set_index("isin")[field].to_dict())
        if "symbol" in f and "symbol" in base:
            part=f.dropna(subset=["symbol"]).drop_duplicates("symbol",keep="last")
            fallback=base["symbol"].astype(str).str.upper().map(part.set_index("symbol")[field].to_dict())
            mapped=mapped.where(mapped.notna(),fallback)
        if field not in base: base[field]=mapped
        else: base[field]=base[field].where(base[field].notna(),mapped)
    base["fundamentals_match"]=base.get("pe",pd.Series(index=base.index,dtype=float)).notna()
    return base

def _run_daily_ai(ranked,out_dir):
    key=os.getenv("GEMINI_API_KEY")
    if not key:
        return {"status":"NOT_CONFIGURED","reports_written":0,"note":"Add GEMINI_API_KEY to GitHub Actions secrets for scheduled AI diligence."}
    try: limit=max(0,min(5,int(os.getenv("VALUEFORGE_AI_DAILY_LIMIT","2"))))
    except ValueError: limit=2
    candidates=ranked[ranked["research_status"]=="VALUE_RESEARCH_CANDIDATE"].head(limit)
    if candidates.empty:
        return {"status":"NO_CANDIDATES","reports_written":0}
    from .agents import run_ai_committee
    report_dir=Path(out_dir)/"reports"
    report_dir.mkdir(parents=True,exist_ok=True)
    written=[]; partial=[]
    for _,row in candidates.iterrows():
        company=row.to_dict()
        report,meta=run_ai_committee(company,api_key=key)
        symbol=re.sub(r"[^A-Za-z0-9_-]","_",str(company.get("symbol","company")))
        exchange=re.sub(r"[^A-Za-z0-9_-]","_",str(company.get("exchange","ex")))
        day=str(company.get("snapshot_date",pd.Timestamp.now().date())).replace("-","")
        path=report_dir/f"{day}_{exchange}_{symbol}.md"
        path.write_text(report,encoding="utf-8")
        written.append(str(path))
        if meta.get("agents_run",0)<4: partial.append(symbol)
    return {"status":"COMPLETED" if not partial else "PARTIAL","reports_written":len(written),"reports":written,"partial_symbols":partial}

def run_daily_scan(market_path="data/live/market_latest.csv",fundamentals_path=FUNDAMENTALS_PATH,output_dir="data/live"):
    market=load_market_snapshot(market_path)
    if market.empty: raise RuntimeError("No market snapshot found. Run the market refresh workflow first.")
    fundamentals=load_fundamentals(fundamentals_path)
    merged=merge_market_and_fundamentals(market,fundamentals)
    result=screen_universe(merged)
    out=Path(output_dir)
    out.mkdir(parents=True,exist_ok=True)
    ranked=result.companies.sort_values(["value_score","volume"],ascending=[False,False],na_position="last")
    ranked.to_csv(out/"daily_research.csv",index=False)
    ai_status=_run_daily_ai(ranked,out)
    summary={
      "scan_at_utc":pd.Timestamp.now(tz="UTC").isoformat(),
      "market_rows":int(len(market)),
      "fundamental_rows":int(len(fundamentals)),
      "matched_rows":int(merged.get("fundamentals_match",pd.Series(dtype=bool)).sum()),
      "market_date":str(market["snapshot_date"].max()) if "snapshot_date" in market else "unknown",
      **result.summary,
      "ai_research":ai_status,
      "method":"Deterministic all-market value triage plus optional quota-limited LLM diligence; no broker actions."
    }
    (out/"research_status.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    return ranked,summary
