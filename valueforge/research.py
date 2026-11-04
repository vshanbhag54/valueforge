from __future__ import annotations
from pathlib import Path
import json, os, re
import pandas as pd

from .fundamentals import latest_fundamentals, normalize_fundamentals
from .market_data import load_market_snapshot
from .scoring import screen_universe
from .universe import attach_market_prices, load_security_master
from .valuation import apply_intrinsic_valuation

FUNDAMENTALS_PATH=Path("data/fundamentals/company_fundamentals.csv")
XBRL_FUNDAMENTALS_PATH=Path("data/fundamentals/xbrl_fundamentals.csv")


def load_fundamentals(path=FUNDAMENTALS_PATH):
    """Load manual/Screener exports and exchange XBRL history without discarding periods."""
    frames=[]
    manual_path=Path(path)
    if manual_path.exists() and manual_path.stat().st_size:
        frames.append(normalize_fundamentals(pd.read_csv(manual_path),source_label="Manual Screener / repository fundamentals"))
    if Path(XBRL_FUNDAMENTALS_PATH).exists() and Path(XBRL_FUNDAMENTALS_PATH).stat().st_size:
        frames.append(normalize_fundamentals(pd.read_csv(XBRL_FUNDAMENTALS_PATH),source_label="Exchange XBRL filings"))
    return pd.concat(frames,ignore_index=True,sort=False) if frames else pd.DataFrame()


def _company_key(frame):
    isin=frame.get("isin",pd.Series(pd.NA,index=frame.index)).astype("string")
    exchange=frame.get("exchange",pd.Series("UNKNOWN",index=frame.index)).astype("string").fillna("UNKNOWN")
    symbol=frame.get("symbol",pd.Series("UNKNOWN",index=frame.index)).astype("string").fillna("UNKNOWN")
    code=frame.get("security_code",pd.Series(pd.NA,index=frame.index)).astype("string")
    fallback=exchange+":"+symbol
    fallback=fallback.where(code.isna() | (code==""),exchange+":CODE:"+code)
    return isin.where(isin.notna() & (isin!=""),fallback)


def _ttm_xbrl_fundamentals(history):
    """Create TTM rows only from four consecutive discrete quarter filings."""
    if history.empty:
        return history
    df=history.copy()
    df["_period"]=pd.to_datetime(df.get("period_end"),errors="coerce")
    if "period_kind" not in df:
        return pd.DataFrame()
    df["_kind"]=df["period_kind"].astype("string").str.lower()
    df["_company_key"]=_company_key(df)
    df["_asof"]=pd.to_datetime(df.get("data_as_of",df.get("filing_ts")),errors="coerce")
    ttm=[]
    flow_fields=["sales","net_profit","profit_before_tax","finance_cost","operating_profit","ocf","capex"]
    for _,group in df[df["_kind"].str.contains("quarter",na=False)].groupby("_company_key",dropna=False):
        # Select the latest filing revision for each quarter, not the last row
        # encountered in the CSV.
        group=group.sort_values(["_period","_asof"],na_position="first").drop_duplicates("_period",keep="last")
        if len(group)<4: continue
        q=group.tail(4)
        dates=q["_period"].dropna().tolist()
        if len(dates)!=4: continue
        gaps=[(dates[i]-dates[i-1]).days for i in range(1,4)]
        if any(g<60 or g>125 for g in gaps): continue
        latest=q.iloc[-1].drop(labels=["_period","_kind","_company_key","_asof"],errors="ignore").to_dict()
        for field in flow_fields:
            vals=pd.to_numeric(q.get(field,pd.Series(index=q.index,dtype=float)),errors="coerce")
            latest[field]=float(vals.sum()) if vals.notna().all() else float("nan")
        latest["period_kind"]="TTM from 4 discrete quarters"
        latest["period_end"]=dates[-1].strftime("%Y-%m-%d")
        latest["ttm_quarters"]=4
        latest["ttm_period_start"]=dates[0].strftime("%Y-%m-%d")
        if latest.get("sales") and latest.get("sales")>0:
            if pd.notna(latest.get("operating_profit")):
                latest["operating_margin"]=latest["operating_profit"]/latest["sales"]*100
        profit=latest.get("net_profit"); ocf=latest.get("ocf"); capex=latest.get("capex")
        latest["fcf"]=ocf-capex if pd.notna(ocf) and pd.notna(capex) else float("nan")
        if pd.notna(profit) and profit!=0 and pd.notna(ocf):
            latest["ocf_to_net_profit"]=ocf/profit
        pbt=latest.get("profit_before_tax"); finance=latest.get("finance_cost")
        if pd.notna(pbt) and pd.notna(finance) and finance>0:
            latest["interest_coverage"]=(pbt+finance)/finance
        # Recalculate return ratios from TTM earnings and balance-sheet capital;
        # never reuse a single-quarter ROE/ROCE in a TTM record.
        equity=pd.to_numeric(pd.Series([latest.get("equity")]),errors="coerce").iloc[0]
        debt=pd.to_numeric(pd.Series([latest.get("total_debt")]),errors="coerce").iloc[0]
        # A TTM return needs the balance-sheet opening point immediately before
        # the first of the four included quarters. Do not approximate it with
        # the third quarter's closing balance.
        opening=group.iloc[-5] if len(group)>=5 else None
        opening_equity=pd.to_numeric(pd.Series([opening.get("equity") if opening is not None else None]),errors="coerce").iloc[0]
        opening_debt=pd.to_numeric(pd.Series([opening.get("total_debt") if opening is not None else None]),errors="coerce").iloc[0]
        if pd.notna(profit) and pd.notna(equity) and pd.notna(opening_equity) and equity>0 and opening_equity>0:
            latest["roe"]=profit/((equity+opening_equity)/2)*100
        # ROCE uses average opening/closing capital employed for the full TTM.
        if (pd.notna(pbt) and pd.notna(finance) and pd.notna(equity) and pd.notna(debt)
                and pd.notna(opening_equity) and pd.notna(opening_debt)):
            current_capital=equity+debt
            opening_capital=opening_equity+opening_debt
            average_capital=(current_capital+opening_capital)/2
            if average_capital>0:
                latest["roce"]=(pbt+finance)/average_capital*100
        latest["source_label"]="Exchange XBRL filings (TTM derived from 4 quarters)"
        ttm.append(latest)
    return pd.DataFrame(ttm)


def _latest_xbrl(history):
    if history.empty: return pd.DataFrame()
    ttm=_ttm_xbrl_fundamentals(history)
    annual=history[history.get("period_kind",pd.Series("",index=history.index)).astype("string").str.lower().str.contains("annual",na=False)].copy()
    if not ttm.empty:
        combined=pd.concat([annual,ttm],ignore_index=True,sort=False)
        chosen=latest_fundamentals(combined)
        ttm_keys=set(_company_key(ttm).tolist())
        key=_company_key(chosen)
        for ix,row in chosen.iterrows():
            if key.loc[ix] in ttm_keys:
                match=ttm.loc[_company_key(ttm)==key.loc[ix]]
                if not match.empty:
                    for col in match.columns:
                        if col in chosen and pd.notna(match.iloc[-1].get(col)):
                            chosen.at[ix,col]=match.iloc[-1][col]
    else:
        source=annual if not annual.empty else history
        chosen=latest_fundamentals(source)

    # Five-year growth requires six annual statements (five full intervals)
    # with no missing/abnormally spaced year. A two- or four-year CAGR is not
    # mislabeled as five-year growth.
    if not chosen.empty and not annual.empty:
        annual=annual.copy()
        annual["_period"]=pd.to_datetime(annual.get("period_end"),errors="coerce")
        annual["_asof"]=pd.to_datetime(annual.get("data_as_of"),errors="coerce")
        annual["_company_key"]=_company_key(annual)
        growth={}
        for company_key,group in annual.groupby("_company_key",dropna=False):
            group=group.dropna(subset=["_period"]).sort_values(
                ["_period","_asof"],na_position="first"
            ).drop_duplicates("_period",keep="last")
            if len(group)<6: continue
            sample=group.tail(6)
            dates=sample["_period"].tolist()
            gaps=[(dates[i]-dates[i-1]).days for i in range(1,6)]
            years=(dates[-1]-dates[0]).days/365.25
            if any(g<300 or g>430 for g in gaps) or not 4.5<=years<=5.5:
                continue
            earliest=sample.iloc[0]
            latest=sample.iloc[-1]
            item={"sales_cagr_years":round(years,2),"profit_cagr_years":round(years,2)}
            for field,target in [("sales","sales_cagr_5y"),("net_profit","profit_cagr_5y")]:
                begin=pd.to_numeric(pd.Series([earliest.get(field)]),errors="coerce").iloc[0]
                finish=pd.to_numeric(pd.Series([latest.get(field)]),errors="coerce").iloc[0]
                if pd.notna(begin) and pd.notna(finish) and begin>0 and finish>0:
                    item[target]=((finish/begin)**(1/years)-1)*100
            growth[company_key]=item
        if growth:
            chosen_keys=_company_key(chosen)
            for col in ["sales_cagr_5y","profit_cagr_5y","sales_cagr_years","profit_cagr_years"]:
                if col not in chosen: chosen[col]=float("nan")
            for ix,company_key in chosen_keys.items():
                if company_key in growth:
                    for col,value in growth[company_key].items():
                        chosen.at[ix,col]=value
    return chosen


def _attach_source(base,frame,override=False):
    if frame.empty: return base
    f=latest_fundamentals(frame)
    for field in f.columns:
        if field in {"isin","symbol","security_code","name","exchange","_company_key"}: continue
        mapped=pd.Series(index=base.index,dtype=object)
        if "isin" in f and "isin" in base:
            part=f.dropna(subset=["isin"]).drop_duplicates("isin",keep="last")
            mapped=base["isin"].astype("string").map(part.set_index("isin")[field].to_dict())
        if "symbol" in f and "symbol" in base:
            part=f.dropna(subset=["symbol"]).drop_duplicates("symbol",keep="last")
            fallback=base["symbol"].astype(str).str.upper().map(part.set_index("symbol")[field].to_dict())
            mapped=mapped.where(mapped.notna(),fallback)
        if "security_code" in f and "security_code" in base:
            part=f.dropna(subset=["security_code"]).drop_duplicates("security_code",keep="last")
            fallback=base["security_code"].astype("string").map(part.set_index("security_code")[field].to_dict())
            mapped=mapped.where(mapped.notna(),fallback)
        if field not in base:
            base[field]=mapped
        elif override:
            base[field]=mapped.where(mapped.notna(),base[field])
        else:
            base[field]=base[field].where(base[field].notna(),mapped)
    return base


def _derive_market_valuation(frame):
    base=frame.copy()
    close=pd.to_numeric(base.get("close",pd.Series(index=base.index,dtype=float)),errors="coerce")
    capital=pd.to_numeric(base.get("paid_up_capital",pd.Series(index=base.index,dtype=float)),errors="coerce")
    face=pd.to_numeric(base.get("face_value",pd.Series(index=base.index,dtype=float)),errors="coerce")
    shares=(capital*10_000_000/face).where((capital>0)&(face>0))
    market_cap=close*shares/10_000_000
    if "market_cap_cr" not in base: base["market_cap_cr"]=market_cap
    else: base["market_cap_cr"]=base["market_cap_cr"].where(base["market_cap_cr"].notna(),market_cap)
    net_profit=pd.to_numeric(base.get("net_profit",pd.Series(index=base.index,dtype=float)),errors="coerce")
    equity=pd.to_numeric(base.get("equity",pd.Series(index=base.index,dtype=float)),errors="coerce")
    period_kind=base.get("period_kind",pd.Series("",index=base.index)).astype("string").str.lower()
    earnings_period_ok=period_kind.str.contains("annual|ttm",regex=True,na=False)
    # Quarterly PAT/EPS are never multiplied into an apparent annual P/E.
    calculated_pe=(market_cap/net_profit.where(net_profit>0)).where(earnings_period_ok)
    calculated_pb=market_cap/equity.where(equity>0)
    if "pe" not in base: base["pe"]=calculated_pe
    else: base["pe"]=base["pe"].where(base["pe"].notna(),calculated_pe)
    if "pb" not in base: base["pb"]=calculated_pb
    else: base["pb"]=base["pb"].where(base["pb"].notna(),calculated_pb)
    eps=pd.to_numeric(base.get("basic_eps",pd.Series(index=base.index,dtype=float)),errors="coerce")
    eps_pe=(close/eps.where(eps>0)).where(earnings_period_ok)
    base["pe"]=base["pe"].where(base["pe"].notna(),eps_pe)
    return base


def merge_market_and_fundamentals(market,fundamentals):
    base=market.copy()
    if fundamentals.empty:
        base["source_label"]="Market data only"
        base["fundamentals_match"]=False
        return base
    f=fundamentals.copy()
    labels=f.get("source_label",pd.Series("",index=f.index)).astype("string").str.lower()
    xbrl=f[labels.str.contains("xbrl",na=False)].copy()
    manual=f[~labels.str.contains("xbrl",na=False)].copy()
    # XBRL history is reduced to verified four-quarter TTM or audited annual data.
    base=_attach_source(base,_latest_xbrl(xbrl),override=False)
    # Explicit user/Screener exports take precedence for supplied ratios, while
    # exchange XBRL remains the auditable source for all other metrics.
    base=_attach_source(base,manual,override=True)
    base=_derive_market_valuation(base)
    base=apply_intrinsic_valuation(base)
    base["fundamentals_match"]=base.get("period_end",pd.Series(index=base.index,dtype=object)).notna()
    return base


def _run_daily_ai(ranked,out_dir):
    key=os.getenv("GEMINI_API_KEY")
    if not key:
        return {"status":"NOT_CONFIGURED","reports_written":0,"note":"Add GEMINI_API_KEY to GitHub Actions secrets for quota-limited AI diligence."}
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


def latest_market_snapshot_date(market):
    """Return the newest valid snapshot date despite missing dates on unpriced listings."""
    if "snapshot_date" not in market.columns:
        return "unknown"
    dates=pd.to_datetime(market["snapshot_date"],errors="coerce",utc=True)
    latest=dates.max()
    return latest.strftime("%Y-%m-%d") if pd.notna(latest) else "unknown"


def run_daily_scan(market_path="data/live/market_latest.csv",fundamentals_path=FUNDAMENTALS_PATH,output_dir="data/live"):
    market=load_market_snapshot(market_path)
    if market.empty: raise RuntimeError("No market snapshot found. Run the market refresh workflow first.")
    security_master=load_security_master()
    master_status_path=Path("data/master/security_master_status.json")
    master_status=json.loads(master_status_path.read_text(encoding="utf-8")) if master_status_path.exists() else {}
    if not security_master.empty:
        market=attach_market_prices(security_master,market)
    fundamentals=load_fundamentals(fundamentals_path)
    merged=merge_market_and_fundamentals(market,fundamentals)
    result=screen_universe(merged)
    out=Path(output_dir)
    out.mkdir(parents=True,exist_ok=True)
    ranked=result.companies.sort_values(["value_score","turnover"],ascending=[False,False],na_position="last")
    ranked.to_csv(out/"daily_research.csv",index=False)
    ai_status=_run_daily_ai(ranked,out)
    status_path=Path("data/live/filings_status.json")
    filing_status=json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
    summary={
      "scan_at_utc":pd.Timestamp.now(tz="UTC").isoformat(),
      "market_rows":int(len(market)),
      "listed_security_master_rows":int(len(security_master)),
      "security_master_status":master_status,
      "eod_price_available":int(market.get("price_status",pd.Series("EOD_PRICE_AVAILABLE",index=market.index)).eq("EOD_PRICE_AVAILABLE").sum()),
      "fundamental_rows":int(len(fundamentals)),
      "matched_rows":int(merged.get("fundamentals_match",pd.Series(dtype=bool)).sum()),
      "fundamentals_match_pct":round(100*int(merged.get("fundamentals_match",pd.Series(dtype=bool)).sum())/max(len(merged),1),2),
      "unpriced_listed_rows":int(market.get("price_status",pd.Series("EOD_PRICE_AVAILABLE",index=market.index)).eq("NO_EOD_PRICE").sum()),
      "market_date":latest_market_snapshot_date(market),
      "filings_status":filing_status,
      **result.summary,
      "ai_research":ai_status,
      "method":"EOD cross-sectional market screen + XBRL/Screener fundamentals + TTM calculations + optional quota-limited specialist diligence; research only."
    }
    (out/"research_status.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    return ranked,summary
