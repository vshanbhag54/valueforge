from __future__ import annotations

from datetime import date, datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import re

import pandas as pd
import requests

NSE_EQUITY_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
BSE_SCRIP_LIST_URL = "https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w"
NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/csv,application/csv,application/octet-stream,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}
BSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.bseindia.com",
    "Referer": "https://www.bseindia.com/",
    "Sec-Fetch-Site": "same-site",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "sec-ch-ua": '"Chromium";v="155", "Not(A:Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}

class UniverseError(RuntimeError):
    pass


def _clean(frame):
    df = frame.copy()
    df.columns = [re.sub(r"[^a-z0-9]+", "_", str(c).strip().lower()).strip("_") for c in df.columns]
    return df


def _first(frame, aliases, default=None):
    for key in aliases:
        if key in frame.columns:
            return frame[key]
    return pd.Series(default, index=frame.index)


def normalize_nse_equity(raw):
    df = _clean(raw)
    out = pd.DataFrame(index=df.index)
    out["symbol"] = _first(df, ["symbol", "nse_symbol"]).astype("string").str.strip().str.upper()
    out["name"] = _first(df, ["name_of_company", "company_name", "name"]).astype("string").str.strip()
    out["exchange"] = "NSE"
    out["isin"] = _first(df, ["isin_number", "isin", "isin_code"]).astype("string").str.strip().str.upper()
    out["series"] = _first(df, ["series"]).astype("string").str.strip().str.upper()
    out["security_code"] = pd.NA
    out["face_value"] = pd.to_numeric(_first(df, ["face_value"]), errors="coerce")
    paid = pd.to_numeric(_first(df, ["paid_up_value", "paid_up_capital"]), errors="coerce")
    # NSE EQUITY_L "PAID UP VALUE" is normally a per-share paid-up value,
    # not company aggregate paid-up capital. Do not map it into paid_up_capital.
    out["paid_up_value_per_share"] = paid
    out["security_status"] = "Available for equity segment"
    out["master_source"] = NSE_EQUITY_URL
    return out


def _records_from_bse(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("Table", "table", "data", "Data", "scrips", "Scrips"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    raise UniverseError(f"Unrecognised BSE security-master payload: {type(payload).__name__}")


def normalize_bse_equity(records):
    df = _clean(pd.DataFrame(records))
    if df.empty:
        raise UniverseError("BSE returned an empty equity scrip master.")
    out = pd.DataFrame(index=df.index)
    out["symbol"] = _first(df, ["scrip_id", "tradingsymbol", "trading_symbol", "symbol", "security_id"]).astype("string").str.strip().str.upper()
    out["name"] = _first(df, ["scrip_name", "company_name", "security_name", "name", "slongname"]).astype("string").str.strip()
    out["exchange"] = "BSE"
    out["isin"] = _first(df, ["isin_number", "isin", "isin_code"]).astype("string").str.strip().str.upper()
    out["series"] = _first(df, ["group", "group_name", "scrip_group", "series"]).astype("string").str.strip().str.upper()
    out["sector"] = _first(df, ["industry", "industry_name", "sector", "industryname"]).astype("string").str.strip()
    out["security_code"] = _first(df, ["scrip_cd", "scrip_code", "security_code", "scripcode"]).astype("string").str.strip()
    face = pd.to_numeric(_first(df, ["face_value", "parval"]), errors="coerce")
    # Standard BSE EQ SCRIP master expresses face value in paise.
    out["face_value"] = face.where(face.isna(), face / 100)
    out["paid_up_value_per_share"] = pd.NA
    out["security_status"] = _first(df, ["status", "scrip_status", "security_status"], "Active").astype("string")
    out["master_source"] = BSE_SCRIP_LIST_URL
    return out


def _request_nse(session):
    response = session.get(NSE_EQUITY_URL, headers=NSE_HEADERS, timeout=30)
    response.raise_for_status()
    if len(response.content) < 1000:
        raise UniverseError(f"NSE equity master response is unexpectedly small ({len(response.content)} bytes).")
    raw = pd.read_csv(BytesIO(response.content))
    return normalize_nse_equity(raw)


def _request_bse(session):
    response = session.get(
        BSE_SCRIP_LIST_URL,
        params={"segment": "Equity"},
        headers=BSE_HEADERS,
        timeout=45,
    )
    response.raise_for_status()
    return normalize_bse_equity(_records_from_bse(response.json()))


def fetch_security_master(today=None):
    """Fetch official NSE available-equity list and BSE equity scrip list.

    Each exchange source fails independently; the returned status states whether
    the universe is combined or partial. Never present a one-exchange file as
    a complete NSE+BSE master.
    """
    today = today or date.today()
    session = requests.Session()
    frames = []
    source_status = {}
    try:
        try:
            nse = _request_nse(session)
            nse = nse.dropna(subset=["symbol"])
            source_status["NSE"] = {"status": "OK", "rows": int(len(nse)), "source": NSE_EQUITY_URL}
            frames.append(nse)
        except Exception as exc:
            source_status["NSE"] = {"status": "FAILED", "error": f"{type(exc).__name__}: {exc}", "source": NSE_EQUITY_URL}
        try:
            bse = _request_bse(session)
            bse = bse.dropna(subset=["symbol"])
            source_status["BSE"] = {"status": "OK", "rows": int(len(bse)), "source": BSE_SCRIP_LIST_URL}
            frames.append(bse)
        except Exception as exc:
            source_status["BSE"] = {"status": "FAILED", "error": f"{type(exc).__name__}: {exc}", "source": BSE_SCRIP_LIST_URL}
    finally:
        session.close()

    if not frames:
        raise UniverseError("Both NSE and BSE security-master sources failed: " + json.dumps(source_status))
    master = pd.concat(frames, ignore_index=True, sort=False)
    master["symbol"] = master["symbol"].astype("string").str.strip().str.upper()
    master["isin"] = master["isin"].astype("string").str.strip().str.upper()
    master["master_as_of"] = today.isoformat()
    master = master.drop_duplicates(["exchange", "symbol"], keep="last").reset_index(drop=True)
    master["has_isin"] = master["isin"].notna() & (master["isin"] != "") & (master["isin"] != "NAN")
    exchange_ok = [key for key, value in source_status.items() if value.get("status") == "OK"]
    status = {
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "master_as_of": today.isoformat(),
        "sources": source_status,
        "exchange_sources_ok": exchange_ok,
        "rows": int(len(master)),
        "unique_isins": int(master.loc[master["has_isin"], "isin"].nunique()),
        "coverage": "COMBINED_NSE_BSE" if set(exchange_ok) == {"NSE", "BSE"} else "PARTIAL_EXCHANGE_MASTER",
        "coverage_note": "Exchange-provided equity security master, not a promise of every historical/delisted instrument. Suspended listings remain listed only if the exchange includes them in its source.",
    }
    return master, status


def save_security_master(master, status, base="data/master"):
    root = Path(base)
    root.mkdir(parents=True, exist_ok=True)
    master.to_csv(root / "security_master.csv", index=False)
    (root / "security_master_status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")


def load_security_master(path="data/master/security_master.csv"):
    p = Path(path)
    return pd.read_csv(p) if p.exists() and p.stat().st_size else pd.DataFrame()


def attach_market_prices(master, market):
    """Left-join EOD prices onto exchange listings; retain securities without quotes."""
    if master.empty:
        return market.copy()
    base=master.copy().reset_index(drop=True)
    quotes=market.copy().reset_index(drop=True)
    for frame in (base,quotes):
        frame["exchange"]=frame["exchange"].astype(str).str.upper()
        frame["symbol"]=frame["symbol"].astype(str).str.strip().str.upper()
        if "isin" in frame:
            frame["isin"]=frame["isin"].astype("string").str.strip().str.upper()
    base["_master_row"]=range(len(base))
    # Prefer ISIN, then exchange+symbol, then BSE numeric scrip code.
    if "isin" in base and "isin" in quotes:
        left=base[base["isin"].notna() & ~base["isin"].isin(["","NAN"])].copy()
        right=quotes[quotes["isin"].notna() & ~quotes["isin"].isin(["","NAN"])].copy()
        merged=left.merge(right,on=["exchange","isin"],how="left",suffixes=("","_quote"))
        hit=merged.get("close",pd.Series(index=merged.index,dtype=float)).notna()
        matched_ids=set(merged.loc[hit,"_master_row"])
        missing=base[~base["_master_row"].isin(matched_ids)].copy()
        merged=merged.loc[hit].copy()
    else:
        merged=pd.DataFrame()
        missing=base.copy()
    # Retry unmatched BSE securities using the official six-digit scrip code.
    bse=missing[missing["exchange"]=="BSE"].copy()
    others=missing[missing["exchange"]!="BSE"].copy()
    if not bse.empty and "security_code" in bse:
        bse["_code"]=bse["security_code"].astype("string").str.replace(r"\\.0$","",regex=True)
        q=quotes[quotes["exchange"]=="BSE"].copy()
        q["_code"]=q["symbol"].astype("string").str.replace(r"\\.0$","",regex=True)
        code_join=bse.merge(q,on=["exchange","_code"],how="left",suffixes=("","_quote"))
        code_join=code_join.drop(columns=["_code"],errors="ignore")
        code_hit=code_join.get("close",pd.Series(index=code_join.index,dtype=float)).notna()
        parts=[merged,code_join.loc[code_hit].copy()] if not merged.empty else [code_join.loc[code_hit].copy()]
        bse=bse.loc[~bse["_master_row"].isin(set(code_join.loc[code_hit,"_master_row"]))].drop(columns=["_code"],errors="ignore")
    else:
        parts=[merged] if not merged.empty else []
    if not others.empty:
        symbol_join=others.merge(quotes,on=["exchange","symbol"],how="left",suffixes=("","_quote"))
        parts.append(symbol_join)
    if not bse.empty:
        parts.append(bse.merge(quotes,on=["exchange","symbol"],how="left",suffixes=("","_quote")))
    merged=pd.concat(parts,ignore_index=True,sort=False) if parts else base

    for key in quotes.columns:
        qkey=key+"_quote"
        if qkey in merged:
            if key in merged:
                if key in {"name","symbol","isin","series","sector"}:
                    merged[key]=merged[key].where(merged[key].notna() & (merged[key].astype(str)!=""),merged[qkey])
                else:
                    merged[key]=merged[qkey].where(merged[qkey].notna(),merged[key])
                merged=merged.drop(columns=[qkey])
            else:
                merged=merged.rename(columns={qkey:key})
    merged=merged.drop(columns=["_master_row"],errors="ignore")
    if "snapshot_date" not in merged:
        merged["snapshot_date"]=pd.NA
    merged["price_status"]=merged["close"].notna().map({True:"EOD_PRICE_AVAILABLE",False:"NO_EOD_PRICE"}) if "close" in merged else "NO_EOD_PRICE"
    merged["universe_source"]="NSE + BSE exchange security masters"
    return merged.drop_duplicates(["exchange","symbol"],keep="last").reset_index(drop=True)
