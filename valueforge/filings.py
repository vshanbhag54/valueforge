from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import json
import shutil

import pandas as pd


QUEUE_PATH = Path("data/fundamentals/xbrl_filing_queue.jsonl")
REGISTRY_PATH = Path("data/fundamentals/processed_filings.csv")
FUNDAMENTALS_PATH = Path("data/fundamentals/xbrl_fundamentals.csv")


def _key(record):
    return (record.symbol, record.filing_id or record.xbrl_url or "")


def _exchange(record):
    return "BSE" if str(record.source.value).startswith("bse") else "NSE"


def _registry_keys(registry):
    if registry.empty or "filing_key" not in registry:
        return set()
    return set(registry["filing_key"].dropna().astype(str))


def sync_xbrl_filings(lookback_days=45, limit=60, workers=4, today=None):
    """Discover new NSE/BSE XBRL financial results, fetch a bounded batch and normalize facts.

    Discovery metadata and extracted facts are persisted. Raw XBRL payloads are
    temporary and removed after parsing; they are not committed to the repo.
    """
    try:
        from india_xbrl.bse import BseDiscoveryClient
        from india_xbrl.discovery import DiscoveryClient
        from india_xbrl.fetcher import Fetcher, plan_from_discovery
        from india_xbrl.manifest import DiscoveryIndex, Manifest
        from india_xbrl.store import PayloadStore
        from india_xbrl.transport import RequestsTransport
        from india_xbrl.models import FetchStatus
    except ImportError as exc:
        raise RuntimeError("Install india-xbrl-filings==0.1.1 to enable XBRL ingestion") from exc

    from .xbrl_extract import extract_filing_fundamentals

    today = today or date.today()
    start = today - timedelta(days=max(1, int(lookback_days)))
    root = Path("data/filings")
    cache_dir = root / ".cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)

    transport = RequestsTransport()
    discovery_counts = {"nse": 0, "bse_integrated": 0, "usable_xbrl": 0, "new_queue_records": 0}
    discovery_errors = {}
    try:
        try:
            nse_records = DiscoveryClient(transport).discover(start, today)
            discovery_counts["nse"] = len(nse_records)
        except Exception as exc:
            nse_records = []
            discovery_errors["nse"] = f"{type(exc).__name__}: {exc}"
        try:
            bse_records = BseDiscoveryClient(transport).discover_integrated()
            discovery_counts["bse_integrated"] = len(bse_records)
        except Exception as exc:
            bse_records = []
            discovery_errors["bse_integrated"] = f"{type(exc).__name__}: {exc}"
    finally:
        transport.close()

    records = []
    seen = set()
    for record in nse_records + bse_records:
        url = (record.xbrl_url or "").strip()
        if not record.symbol or not url.lower().endswith(".xml"):
            continue
        if not record.consolidated:
            continue
        key = _key(record)
        if key in seen:
            continue
        seen.add(key)
        records.append(record)
    discovery_counts["usable_xbrl"] = len(records)

    queue = DiscoveryIndex.load(QUEUE_PATH)
    existing_queue = {_key(r) for r in queue.records}
    for record in records:
        if _key(record) not in existing_queue:
            queue.records.append(record)
            existing_queue.add(_key(record))
            discovery_counts["new_queue_records"] += 1
    queue.save(QUEUE_PATH)

    registry = pd.read_csv(REGISTRY_PATH) if REGISTRY_PATH.exists() else pd.DataFrame()
    processed = _registry_keys(registry)
    pending = [r for r in queue.records if _key(r) not in processed and r.xbrl_url and r.consolidated]
    # Historical periods first so the panel builds a multi-year record; the
    # persistent queue prevents older filings from being dropped between runs.
    pending.sort(key=lambda r: (
        r.period_to or date.max,
        r.filing_ts or datetime.max,
        r.symbol
    ))
    batch = pending[:max(0, int(limit))]

    status = {
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "lookback_days": int(lookback_days),
        "batch_limit": int(limit),
        "discovery": discovery_counts,
        "discovery_errors": discovery_errors,
        "queue_total": len(queue.records),
        "pending_before_batch": len(pending),
        "batch_selected": len(batch),
        "downloaded": 0,
        "parsed": 0,
        "parse_failed": 0,
        "fetch_failed": 0,
    }

    if not batch:
        status["state"] = "NO_PENDING_FILINGS" if not pending else "BATCH_LIMIT_ZERO"
        Path("data/live/filings_status.json").parent.mkdir(parents=True, exist_ok=True)
        Path("data/live/filings_status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
        return status

    manifest_path = cache_dir / "manifest.jsonl"
    manifest = Manifest.load(manifest_path)
    store = PayloadStore(cache_dir / "payloads")
    plans = [plan_from_discovery(r) for r in batch]
    record_map = {_key(r): r for r in batch}
    fetch_transport = RequestsTransport()
    try:
        fetcher = Fetcher(
            fetch_transport, store, manifest, workers=max(1, min(int(workers), 6)),
            persist=lambda: manifest.save(manifest_path),
        )
        stats = fetcher.run(plans, skip_standalone_redundant=True)
        status["fetch_stats"] = stats.as_dict()
    finally:
        fetch_transport.close()

    extracted = []
    new_registry_rows = []
    for filing in manifest.records:
        record = record_map.get((filing.symbol, filing.filing_id or filing.xbrl_url or ""))
        if record is None:
            continue
        filing_key = f"{record.symbol}|{record.filing_id or record.xbrl_url}"
        if filing.fetch_status != FetchStatus.OK or not filing.raw_path:
            status["fetch_failed"] += 1
            continue
        status["downloaded"] += 1
        try:
            payload = store.read_raw(filing.raw_path)
            normalized = extract_filing_fundamentals(payload, {
                "symbol": record.symbol,
                "company": record.company,
                "isin": record.isin,
                "exchange": _exchange(record),
                "period_end": record.period_to,
                "relating_to": record.relating_to,
                "filing_ts": record.filing_ts.isoformat() if record.filing_ts else None,
                "xbrl_url": record.xbrl_url,
                "filing_id": record.filing_id,
                "consolidated": record.consolidated,
                "audited": record.audited,
            })
            normalized["filing_key"] = filing_key
            extracted.append(normalized)
            new_registry_rows.append({
                "filing_key": filing_key, "symbol": record.symbol, "company": record.company,
                "exchange": _exchange(record), "isin": normalized.get("isin"),
                "period_end": normalized.get("period_end"), "filing_id": record.filing_id,
                "filing_ts": record.filing_ts.isoformat() if record.filing_ts else None,
                "consolidated": record.consolidated, "audited": record.audited,
                "xbrl_url": record.xbrl_url, "parse_status": "PARSED",
                "fact_count": normalized.get("fact_count", 0),
            })
            status["parsed"] += 1
        except Exception as exc:
            status["parse_failed"] += 1
            new_registry_rows.append({
                "filing_key": filing_key, "symbol": record.symbol, "company": record.company,
                "exchange": _exchange(record), "isin": record.isin,
                "period_end": record.period_to.isoformat() if record.period_to else None,
                "filing_id": record.filing_id,
                "filing_ts": record.filing_ts.isoformat() if record.filing_ts else None,
                "consolidated": record.consolidated, "audited": record.audited,
                "xbrl_url": record.xbrl_url, "parse_status": f"PARSE_FAILED: {type(exc).__name__}: {exc}",
                "fact_count": 0,
            })

    if extracted:
        new_fundamentals = pd.DataFrame(extracted)
        if FUNDAMENTALS_PATH.exists():
            existing_fundamentals = pd.read_csv(FUNDAMENTALS_PATH)
            new_fundamentals = pd.concat([existing_fundamentals, new_fundamentals], ignore_index=True, sort=False)
        if "filing_key" in new_fundamentals:
            new_fundamentals = new_fundamentals.drop_duplicates("filing_key", keep="last")
        new_fundamentals.to_csv(FUNDAMENTALS_PATH, index=False)

    if new_registry_rows:
        updated_registry = pd.concat([registry, pd.DataFrame(new_registry_rows)], ignore_index=True, sort=False)
        updated_registry = updated_registry.drop_duplicates("filing_key", keep="last")
        updated_registry.to_csv(REGISTRY_PATH, index=False)

    # Temporary XBRL payloads are deliberately not retained in Git.
    shutil.rmtree(cache_dir, ignore_errors=True)
    status["pending_after_batch"] = max(0, len(pending) - len(batch))
    status["state"] = "COMPLETED" if not discovery_errors else "COMPLETED_WITH_SOURCE_ERRORS"
    Path("data/live/filings_status.json").parent.mkdir(parents=True, exist_ok=True)
    Path("data/live/filings_status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    return status
