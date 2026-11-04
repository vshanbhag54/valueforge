from __future__ import annotations
from datetime import date, datetime, timezone
from pathlib import Path
import json, re
import pandas as pd

DATASET_ID="tejhq/indian-markets"
PRICE_PATTERN=re.compile(r"^(nse|bse)/year=(\d{4})/(nse|bse)_(\d{4})\.parquet$")

class MarketDataError(RuntimeError): pass

def _hub_files():
    try:
        from huggingface_hub import HfApi
        return list(HfApi().list_repo_files(DATASET_ID,repo_type="dataset"))
    except Exception as exc:
        raise MarketDataError(f"Could not list public dataset files: {exc}") from exc

def _download(filename):
    try:
        from huggingface_hub import hf_hub_download
        return Path(hf_hub_download(repo_id=DATASET_ID,repo_type="dataset",filename=filename))
    except Exception as exc:
        raise MarketDataError(f"Could not download {filename}: {exc}") from exc

def latest_annual_partition(files,exchange,today=None):
    today=today or date.today()
    matches=[]
    for name in files:
        m=PRICE_PATTERN.match(name)
        if m and m.group(1)==exchange and m.group(3)==exchange and int(m.group(2))<=today.year:
            matches.append((int(m.group(2)),name))
    if not matches: raise MarketDataError(f"No {exchange.upper()} annual price rollup published for {today.year} or earlier.")
    return max(matches)[1]

def _read(path):
    try: return pd.read_parquet(path)
    except Exception as exc: raise MarketDataError(f"Parquet read failed for {path.name}: {exc}") from exc

def _as_date(series):
    return pd.to_datetime(series,errors="coerce").dt.date

def download_latest_market_data(today=None,max_age_days=10):
    """Read annual exchange rollups, select latest trading day and join latest derived metrics."""
    today=today or date.today()
    files=_hub_files()
    frames=[]; source_files=[]; dates={}; metric_files=[]
    for ex in ("nse","bse"):
        price_file=latest_annual_partition(files,ex,today)
        price=_read(_download(price_file))
        if "date" not in price or "symbol" not in price:
            raise MarketDataError(f"Unexpected schema in {price_file}; required date and symbol columns.")
        price["date"]=_as_date(price["date"])
        price=price[price["date"].notna() & (price["date"]<=today)]
        allowed={"EQ","BE","BZ"} if ex=="nse" else {"A","B","T"}
        if "series" in price:
            price=price[price["series"].astype(str).str.upper().isin(allowed)]
        if price.empty: raise MarketDataError(f"{ex.upper()} annual file had no supported equity rows.")
        latest_day=price["date"].max()
        age=(today-latest_day).days
        if age>max_age_days:
            raise MarketDataError(f"{ex.upper()} latest EOD date is {latest_day} ({age} days old); refusing stale market data.")
        snapshot=price[price["date"]==latest_day].copy()
        snapshot["exchange"]=ex.upper()
        metric_file=f"metrics/{ex}_latest.parquet"
        if metric_file in files:
            metrics=_read(_download(metric_file))
            if "date" in metrics:
                metrics["date"]=_as_date(metrics["date"])
                metrics=metrics[metrics["date"]==latest_day]
            keys=[k for k in ("date","symbol","isin") if k in snapshot.columns and k in metrics.columns]
            if "date" not in keys or "symbol" not in keys:
                raise MarketDataError(f"Unexpected join keys in {metric_file}; required date and symbol.")
            extras=[c for c in metrics.columns if c not in snapshot.columns and c not in keys]
            snapshot=snapshot.merge(metrics[keys+extras],on=keys,how="left")
            metric_files.append(metric_file)
        else:
            snapshot["metrics_status"]="NOT_AVAILABLE"
        dates[ex.upper()]=str(latest_day)
        source_files.append(price_file)
        frames.append(snapshot)
    out=pd.concat(frames,ignore_index=True,sort=False)
    out.columns=[str(c).lower() for c in out.columns]
    out["exchange"]=out["exchange"].astype(str).str.upper()
    out["symbol"]=out["symbol"].astype(str).str.strip().str.upper()
    out["snapshot_date"]=out["date"].astype(str)
    out=out.drop_duplicates(["exchange","symbol","snapshot_date"],keep="last")
    status={
      "provider":"TejHQ / tejhq-indian-markets (Hugging Face)",
      "dataset_id":DATASET_ID,"data_type":"end_of_day_bhavcopy","intraday":False,
      "retrieved_at_utc":datetime.now(timezone.utc).isoformat(),
      "exchange_dates":dates,"rows":int(len(out)),"source_files":source_files,"metric_files":metric_files,
      "coverage_note":"Daily-traded supported NSE EQ/BE/BZ and BSE A/B/T series in the source dataset; not every listed, suspended or non-trading instrument.",
      "source_url":"https://huggingface.co/datasets/tejhq/indian-markets"
    }
    return out,status

def save_market_snapshot(frame,status,output_dir="data/live"):
    out=Path(output_dir); out.mkdir(parents=True,exist_ok=True)
    frame.to_csv(out/"market_latest.csv",index=False)
    (out/"market_status.json").write_text(json.dumps(status,indent=2),encoding="utf-8")

def load_market_snapshot(path="data/live/market_latest.csv"):
    p=Path(path)
    return pd.read_csv(p) if p.exists() else pd.DataFrame()
