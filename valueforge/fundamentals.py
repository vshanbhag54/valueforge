from __future__ import annotations
import re, math
import pandas as pd

ALIASES={
"symbol":["symbol","nse code","nse symbol","ticker","bse code","code"],
"isin":["isin","isin code","security isin"],"name":["name","company","company name","security name"],
"exchange":["exchange","market"],"sector":["sector","industry"],
"period_end":["period end","period_end","financial year end","reporting date"],
"basis":["basis","reporting basis","consolidated/standalone"],
"data_as_of":["data as of","data_as_of","export date"],"source_url":["source url","source_url","source","url"],
"pe":["p/e","pe","stock p/e","price to earnings"],"pb":["p/b","pb","price to book value","price/book"],
"market_cap_cr":["market cap","market cap rs.cr.","mar cap rs.cr.","market capitalization"],
"roe":["roe","roe %","return on equity","return on equity %"],"roce":["roce","roce %","return on capital employed","return on capital employed %"],
"debt_to_equity":["debt to equity","debt/equity","debt-equity","debt to equity ratio"],
"interest_coverage":["interest coverage","interest coverage ratio"],
"operating_margin":["operating margin","operating profit margin","opm","opm %"],
"ocf_to_net_profit":["ocf to net profit","operating cash flow / net profit","cash conversion"],
"sales_cagr_5y":["sales cagr 5y","sales growth 5years","sales growth 5 years"],
"profit_cagr_5y":["profit cagr 5y","profit growth 5years","profit growth 5 years"],
"promoter_pledge_pct":["promoter pledge","pledged promoter holding","promoter holding pledged"],
"promoter_holding_pct":["promoter holding","promoters %","promoter holding %"],
"net_profit":["net profit","net profit rs.cr.","profit after tax","pat"],"sales":["sales","sales rs.cr.","revenue","revenue from operations"],
"total_debt":["total debt","borrowings","debt"],"cash":["cash","cash equivalents","cash and bank"],
"equity":["equity","shareholders funds","total equity"],"ocf":["operating cash flow","cash from operations","cash flow from operating activities"],
"fcf":["free cash flow","fcf"],"auditor_qualification":["auditor qualification","auditor opinion","audit opinion"],
"related_party_flags":["related party flags","related party transactions","related party concerns"],
"contingent_liabilities":["contingent liabilities","contingent liability"]
}
NUMERIC={k for k in ALIASES if k not in {"symbol","isin","name","exchange","sector","period_end","basis","data_as_of","source_url","auditor_qualification","related_party_flags","contingent_liabilities"}}

def _key(v): return re.sub(r"[^a-z0-9]+"," ",str(v).lower()).strip()

def parse_number(v):
    if v is None or (isinstance(v,float) and math.isnan(v)): return float("nan")
    if isinstance(v,(int,float)): return float(v)
    s=str(v).strip().replace(",","").replace("₹","").replace("%","")
    s=re.sub(r"(?i)\\b(rs\\.?|cr\\.?|crores?|x)\\b","",s).strip()
    if s.upper() in {"","-","—","NA","N/A","NM"}: return float("nan")
    neg=s.startswith("(") and s.endswith(")")
    try:
        x=float(s.strip("() "))
        return -x if neg else x
    except ValueError: return float("nan")

def normalize_fundamentals(frame,source_label="User-uploaded Screener/export"):
    raw=frame.copy(); lookup={_key(c):c for c in raw.columns}; out=pd.DataFrame(index=raw.index)
    for target,aliases in ALIASES.items():
        col=next((lookup[_key(a)] for a in aliases if _key(a) in lookup),None)
        if col is not None: out[target]=raw[col]
    for field in NUMERIC:
        if field in out: out[field]=out[field].map(parse_number)
    for field in ("symbol","isin","exchange"):
        if field in out: out[field]=out[field].astype(str).str.strip().str.upper()
    if "exchange" not in out: out["exchange"]="UNKNOWN"
    if "basis" not in out: out["basis"]="unknown"
    if "source_url" not in out: out["source_url"]=pd.NA
    if "period_end" in out: out["period_end"]=pd.to_datetime(out["period_end"],errors="coerce").dt.strftime("%Y-%m-%d")
    out["source_label"]=source_label
    out["imported_at_utc"]=pd.Timestamp.now(tz="UTC").isoformat()
    return out.reset_index(drop=True)

def latest_fundamentals(frame):
    if frame.empty: return frame
    df=frame.copy()
    if "period_end" in df:
        df["_period"]=pd.to_datetime(df["period_end"],errors="coerce")
        key="isin" if "isin" in df and df["isin"].notna().any() else "symbol"
        df=df.sort_values("_period").drop_duplicates(key,keep="last").drop(columns="_period")
    return df
