from __future__ import annotations
import math
import re
import pandas as pd

ALIASES={
"symbol":["symbol","nse code","nse symbol","ticker","bse code","code"],
"isin":["isin","isin code","security isin"],"name":["name","company","company name","security name"],
"exchange":["exchange","market"],"sector":["sector","industry"],"security_code":["security code","security_code","scrip code","scrip_cd","bse scrip code"],
"period_end":["period end","period_end","financial year end","reporting date"],
"basis":["basis","reporting basis","consolidated/standalone"],
"data_as_of":["data as of","data_as_of","export date","filed at"],
"source_url":["source url","source_url","source","url"],
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
"capex":["capex","capital expenditure","purchase of property plant and equipment"],"fcf":["free cash flow","fcf"],"auditor_qualification":["auditor qualification","auditor opinion","audit opinion"],
"related_party_flags":["related party flags","related party transactions","related party concerns"],
"contingent_liabilities":["contingent liabilities","contingent liability"],
"basic_eps":["basic eps","eps basic","earnings per share basic"],
"paid_up_capital":["paid up capital","paid up equity share capital"],"face_value":["face value","face value per share"],
"assets":["assets","total assets"],"profit_before_tax":["profit before tax","pbt"],
"finance_cost":["finance cost","finance costs"],"operating_profit":["operating profit"],
"period_kind":["period kind"],"period_days":["period days"],"audited":["audited"],
"filing_id":["filing id"],"filing_key":["filing key"],"taxonomy_family":["taxonomy family"],
"fact_count":["fact count"],"context_count":["context count"],"source_label":["source label"],
"imported_at_utc":["imported at utc"],"unit_currency_note":["unit currency note"]
}
NUMERIC={
"pe","pb","market_cap_cr","roe","roce","debt_to_equity","interest_coverage","operating_margin",
"ocf_to_net_profit","sales_cagr_5y","profit_cagr_5y","promoter_pledge_pct","promoter_holding_pct",
"net_profit","sales","total_debt","cash","equity","ocf","capex","fcf","basic_eps","paid_up_capital",
"face_value","assets","profit_before_tax","finance_cost","operating_profit","period_days","fact_count","context_count"
}

def _key(value):
    return re.sub(r"[^a-z0-9]+"," ",str(value).lower()).strip()

def parse_number(value):
    if value is None or (isinstance(value,float) and math.isnan(value)): return float("nan")
    if isinstance(value,(int,float)): return float(value)
    s=str(value).strip().replace(",","").replace("₹","").replace("%","")
    s=re.sub(r"(?i)\b(rs\.?|cr\.?|crores?|x)\b","",s).strip()
    if s.upper() in {"","-","—","NA","N/A","NM","NONE"}: return float("nan")
    neg=s.startswith("(") and s.endswith(")")
    try:
        x=float(s.strip("() "))
        return -x if neg else x
    except ValueError: return float("nan")

def _clean_identifier(series):
    result=series.astype("string").str.strip().str.upper()
    return result.mask(result.isin(["","NAN","NONE","<NA>"]))

def normalize_fundamentals(frame,source_label="User-uploaded Screener/export"):
    raw=frame.copy()
    lookup={_key(c):c for c in raw.columns}
    out=pd.DataFrame(index=raw.index)
    for target,aliases in ALIASES.items():
        col=next((lookup[_key(a)] for a in aliases if _key(a) in lookup),None)
        if col is not None: out[target]=raw[col]
    # Keep provider-specific columns and filing metadata for auditability.
    for col in raw.columns:
        if col not in out.columns:
            out[col]=raw[col]
    for field in NUMERIC:
        if field in out: out[field]=out[field].map(parse_number)
    for field in ("symbol","isin","exchange","security_code"):
        if field in out: out[field]=_clean_identifier(out[field])
    if "exchange" not in out: out["exchange"]="UNKNOWN"
    if "basis" not in out: out["basis"]="unknown"
    if "source_url" not in out: out["source_url"]=pd.NA
    if "period_end" in out:
        out["period_end"]=pd.to_datetime(out["period_end"],errors="coerce").dt.strftime("%Y-%m-%d")
    out["source_label"]=out.get("source_label",source_label)
    out["imported_at_utc"]=pd.Timestamp.now(tz="UTC").isoformat()
    return out.reset_index(drop=True)

def latest_fundamentals(frame):
    if frame.empty: return frame
    df=frame.copy()
    df["_period"]=pd.to_datetime(df.get("period_end"),errors="coerce")
    if "isin" not in df: df["isin"]=pd.NA
    if "symbol" not in df: df["symbol"]=pd.NA
    if "exchange" not in df: df["exchange"]="UNKNOWN"
    df["_company_key"]=df["isin"].astype("string")
    fallback=df["exchange"].astype("string").fillna("UNKNOWN")+":"+df["symbol"].astype("string").fillna("UNKNOWN")
    if "security_code" in df:
        code=df["security_code"].astype("string")
        fallback=fallback.where(code.isna() | (code==""),df["exchange"].astype("string").fillna("UNKNOWN")+":CODE:"+code)
    df["_company_key"]=df["_company_key"].where(df["_company_key"].notna() & (df["_company_key"]!=""),fallback)
    asof=pd.to_datetime(df.get("data_as_of",df.get("imported_at_utc")),errors="coerce")
    df["_asof"]=asof
    basis=df.get("basis",pd.Series("unknown",index=df.index)).astype("string").str.lower()
    df["_basis_priority"]=basis.map({"consolidated":2,"standalone":1}).fillna(0)
    label=df.get("source_label",pd.Series("",index=df.index)).astype("string").str.lower()
    df["_source_priority"]=label.map(lambda x: 2 if "screener" in x or "manual" in x or "user" in x else 1)
    df=df.sort_values(["_company_key","_period","_basis_priority","_asof","_source_priority"],ascending=[True,False,False,False,False],na_position="last")
    df=df.drop_duplicates("_company_key",keep="first")
    return df.drop(columns=["_period","_company_key","_asof","_basis_priority","_source_priority"],errors="ignore").reset_index(drop=True)
