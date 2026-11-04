from __future__ import annotations
from datetime import date, datetime, timezone
from pathlib import Path
import json, re
import pandas as pd

DATASET_ID="tejhq/indian-markets"
PATTERN=re.compile(r"^(nse|bse)/year=(\d{4})/month=(\d{2})/date=(\d{4}-\d{2}-\d{2})\.parquet$")

class MarketDataError(RuntimeError): pass

def _hub_files():
    try:
        from huggingface_hub import HfApi
        return list(HfApi().list_repo_files(DATASET_ID, repo_type="dataset"))
    except Exception as exc:
        raise MarketDataError(f"Could not list public dataset files: {exc}") from exc

def _download(filename):
    try:
        from huggingface_hub import hf_hub_download
        return Path(hf_hub_download(repo_id=DATASET_ID, repo_type="dataset", filename=filename))
    except Exception as exc:
        raise MarketDataError(f"Could not download {filename}: {exc}") from exc

def latest_partition(files, exchange, today=None, max_age_days=10):
    today=today or date.today()
    matches=[]
    for name in files:
        m=PATTERN.match(name)
        if m and m.group(1)==exchange:
            d=date.fromisoformat(m.group(4))
            if d<=today and (today-d).days<=max_age_days: matches.append((d,name))
    if not matches: raise MarketDataError(f"No {exchange.upper()} EOD partition in last {max_age_days} days.")
    return max(matches)[1]

def _read(path):
    try: return pd.read_parquet(path)
    except Exception as exc: raise MarketDataError(f"Parquet read failed for {path.name}: {exc}") from exc

def download_latest_market_data(today=None):
    files=_hub_files()
    frames=[]; source_files=[]; dates={}
    for ex in ("nse","bse"):
        part=latest_partition(files,ex,today)
        price=_read(_download(part))
        price["exchange"]=ex.upper()
        price["date"]=pd.to_datetime(price["date"],errors="coerce").dt.date
        allowed={"EQ","BE","BZ"} if ex=="nse" else {"A","B","T"}
        if "series" in price: price=price[price["series"].astype(str).str.upper().isin(allowed)]
        part_date=PATTERN.match(part).group(4)
        metric_name=f"metrics/{ex}_{part_date[:4]}.parquet"
        if metric_name in files:
            metrics=_read(_download(metric_name))
            metrics["date"]=pd.to_datetime(metrics["date"],errors="coerce").dt.date
            target=price["date"].max()
            metrics=metrics[metrics["date"]==target]
            keys=[k for k in ("date","symbol","isin") if k in price and k in metrics]
            if keys:
                extras=[k for k in metrics.columns if k not in price.columns]
                price=price.merge(metrics[keys+extras],on=keys,how="left")
        else:
            price["metrics_status"]="NOT_AVAILABLE"
        if price.empty: raise MarketDataError(f"{ex.upper()} EOD file contained no supported equity rows.")
        dates[ex.upper()]=str(price["date"].max())
        source_files.append(part)
        frames.append(price)
    out=pd.concat(frames,ignore_index=True,sort=False)
    out.columns=[str(c).lower() for c in out.columns]
    out["symbol"]=out["symbol"].astype(str).str.strip().str.upper()
    out["snapshot_date"]=out["date"].astype(str)
    out=out.drop_duplicates(["exchange","symbol","snapshot_date"],keep="last")
    status={
      "provider":"TejHQ / tejhq-indian-markets (Hugging Face)",
      "dataset_id":DATASET_ID,"data_type":"end_of_day_bhavcopy","intraday":False,
      "retrieved_at_utc":datetime.now(timezone.utc).isoformat(),
      "exchange_dates":dates,"rows":int(len(out)),"source_files":source_files,
      "coverage_note":"Daily-traded supported equity series from this dataset; not every listed, suspended or non-trading security.",
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
