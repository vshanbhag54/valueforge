from __future__ import annotations
from dataclasses import dataclass
import math
import pandas as pd

FIELDS=["pe","pb","roe","roce","debt_to_equity","interest_coverage","operating_margin","ocf_to_net_profit","sales_cagr_5y","profit_cagr_5y","promoter_pledge_pct","promoter_holding_pct","net_profit","sales","total_debt","cash","equity","ocf","fcf"]
@dataclass
class ScreeningResult:
    companies: pd.DataFrame
    summary: dict

def number(v):
    try:
        x=float(v)
        return x if math.isfinite(x) else float("nan")
    except (TypeError,ValueError): return float("nan")

def scale(v,low,high,inverse=False):
    x=number(v)
    if math.isnan(x): return float("nan")
    if inverse: return max(0.0,min(100.0,100*(high-x)/(high-low)))
    return max(0.0,min(100.0,100*(x-low)/(high-low)))

def score_company(r):
    value=[]; quality=[]; risk=[]
    pe=number(r.get("pe"))
    if not math.isnan(pe) and pe>0: value.append(scale(pe,6,30,True) if pe>=6 else 55.0)
    pb=number(r.get("pb"))
    if not math.isnan(pb) and pb>0: value.append(scale(pb,.7,5,True) if pb>=.7 else 60.0)
    for k,lo,hi in [("roe",8,22),("roce",8,24),("operating_margin",5,25),("sales_cagr_5y",0,20),("profit_cagr_5y",0,25)]:
        v=scale(r.get(k),lo,hi)
        if not math.isnan(v): quality.append(v)
    cash=scale(r.get("ocf_to_net_profit"),.25,1.25)
    if not math.isnan(cash): quality.append(cash)
    for k,lo,hi in [("debt_to_equity",0,2),("promoter_pledge_pct",0,25)]:
        v=scale(r.get(k),lo,hi,True)
        if not math.isnan(v): risk.append(v)
    v=scale(r.get("interest_coverage"),1,8)
    if not math.isnan(v): risk.append(v)
    parts=[]
    for vals,w in ((value,.45),(quality,.35),(risk,.20)):
        if vals: parts.append((sum(vals)/len(vals),w))
    score=sum(v*w for v,w in parts)/sum(w for _,w in parts) if parts else float("nan")
    coverage=sum(not math.isnan(number(r.get(k))) for k in ("pe","roe","roce","debt_to_equity","ocf_to_net_profit","promoter_pledge_pct"))
    return (round(score,1) if not math.isnan(score) else float("nan"),int(coverage))

def financial_sector(sector):
    s=str(sector or "").lower()
    return any(x in s for x in ("bank","nbfc","finance","financial","insurance","lending"))

def screen_universe(frame):
    df=frame.copy()
    for k in FIELDS:
        if k not in df: df[k]=float("nan")
        df[k]=pd.to_numeric(df[k],errors="coerce")
    pairs=df.apply(lambda r:score_company(r.to_dict()),axis=1)
    df["value_score"]=[x[0] for x in pairs]; df["fundamental_coverage"]=[x[1] for x in pairs]
    def status(r):
        if financial_sector(r.get("sector")): return "SECTOR_MODEL_REQUIRED"
        if r["fundamental_coverage"]<4: return "FUNDAMENTALS_INCOMPLETE"
        if pd.isna(r.get("period_end")): return "PERIOD_NOT_VERIFIED"
        p=pd.to_datetime(r.get("period_end"),errors="coerce")
        if pd.isna(p): return "PERIOD_NOT_VERIFIED"
        if (pd.Timestamp.now().normalize()-p.normalize()).days>450: return "FUNDAMENTALS_STALE"
        if pd.isna(r.get("pe")) or pd.isna(r.get("roe")) or pd.isna(r.get("debt_to_equity")): return "FUNDAMENTALS_INCOMPLETE"
        if pd.notna(r.get("net_profit")) and r.get("net_profit")<=0: return "LOSS_MAKING_REVIEW"
        if pd.notna(r.get("promoter_pledge_pct")) and r.get("promoter_pledge_pct")>=25: return "GOVERNANCE_REVIEW"
        if pd.notna(r.get("debt_to_equity")) and r.get("debt_to_equity")>2: return "LEVERAGE_REVIEW"
        if r["value_score"]>=65: return "VALUE_RESEARCH_CANDIDATE"
        if r["value_score"]>=50: return "VALUE_WATCHLIST"
        return "NOT_QUALIFIED"
    df["research_status"]=df.apply(status,axis=1)
    df["is_price_only"]=df["pe"].isna()
    counts=df["research_status"].value_counts().to_dict()
    return ScreeningResult(df,{"total":len(df),"research_candidates":int(counts.get("VALUE_RESEARCH_CANDIDATE",0)),
      "watchlist":int(counts.get("VALUE_WATCHLIST",0)),"fundamentals_incomplete":int(counts.get("FUNDAMENTALS_INCOMPLETE",0)),
      "price_only":int(df["is_price_only"].sum()),"by_status":counts})
