from dataclasses import dataclass
import math
import pandas as pd

FIELDS=["pe","pb","roe","roce","debt_to_equity","interest_coverage","operating_margin","ocf_to_net_profit","market_cap_cr"]
@dataclass
class ScreeningResult:
    companies: pd.DataFrame
    summary: dict

def num(v):
    try:
        x=float(v); return x if math.isfinite(x) else float("nan")
    except (TypeError,ValueError): return float("nan")

def scale(v,good,bad):
    x=num(v)
    if math.isnan(x): return float("nan")
    return max(0.0,min(100.0,100*(x-bad)/(good-bad)))

def score_company(r):
    parts=[]
    for k,g,b in [("roe",20,5),("roce",22,5),("interest_coverage",8,1.5),("ocf_to_net_profit",1.2,0.3),("operating_margin",25,5)]:
        x=scale(r.get(k),g,b)
        if not math.isnan(x): parts.append(x)
    de=num(r.get("debt_to_equity"))
    if not math.isnan(de): parts.append(max(0,min(100,100-de*35)))
    pe=num(r.get("pe"))
    if not math.isnan(pe) and pe>0: parts.append(max(0,min(100,100-max(0,pe-5)*1.6)))
    pb=num(r.get("pb"))
    if not math.isnan(pb) and pb>0: parts.append(max(0,min(100,100-max(0,pb-1)*12)))
    return (round(sum(parts)/len(parts),1),len(parts)) if parts else (float("nan"),0)

def screen_universe(frame,min_roe=12,max_de=1.0,max_pe=30):
    df=frame.copy()
    for k in FIELDS: df[k]=pd.to_numeric(df[k],errors="coerce") if k in df else float("nan")
    results=df.apply(lambda r:score_company(r.to_dict()),axis=1)
    df["value_score"]=[x[0] for x in results]; df["evidence_count"]=[x[1] for x in results]
    def status(r):
        if r.evidence_count<3: return "INSUFFICIENT_DATA"
        if pd.isna(r.roe) or pd.isna(r.debt_to_equity): return "REVIEW_DATA"
        if r.roe<min_roe or r.debt_to_equity>max_de: return "FILTERED"
        if pd.notna(r.pe) and r.pe>max_pe: return "FILTERED"
        return "QUALIFIED_FOR_RESEARCH"
    df["screen_status"]=df.apply(status,axis=1)
    def provenance(r):
        for k in ["source_url","period_end","basis","data_as_of"]:
            if k not in df or pd.isna(r.get(k)): return "PROVENANCE_INCOMPLETE"
        return "PROVENANCE_PRESENT"
    df["data_status"]=df.apply(provenance,axis=1)
    return ScreeningResult(df,{"qualified":int((df.screen_status=="QUALIFIED_FOR_RESEARCH").sum()),
      "insufficient_data":int(df.screen_status.isin(["INSUFFICIENT_DATA","REVIEW_DATA"]).sum()),
      "filtered":int((df.screen_status=="FILTERED").sum())})
