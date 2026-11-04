from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
import math
import os
import re
from typing import Any

import pandas as pd


def database_url() -> str | None:
    return os.getenv("VALUEFORGE_DATABASE_URL") or os.getenv("DATABASE_URL")


def database_configured() -> bool:
    return bool(database_url())


def _missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _scalar(value: Any) -> Any:
    if _missing(value):
        return None
    if hasattr(value, "item"):
        try:
            value = value.item()
        except (ValueError, TypeError):
            pass
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, pd.Series):
        return _jsonable(value.to_dict())
    return _scalar(value)


def _json(value: Any) -> str:
    return json.dumps(_jsonable(value), ensure_ascii=False, separators=(",", ":"))


def company_key(row: dict) -> str | None:
    isin = str(_scalar(row.get("isin")) or "").strip().upper()
    if re.fullmatch(r"IN[A-Z0-9]{10}", isin):
        return isin
    exchange = str(_scalar(row.get("exchange")) or "").strip().upper()
    code = str(_scalar(row.get("security_code")) or "").strip()
    symbol = str(_scalar(row.get("symbol")) or "").strip().upper()
    if not exchange:
        return None
    if code:
        return f"{exchange}:CODE:{code}"
    if symbol:
        return f"{exchange}:{symbol}"
    return None


def _flag(value) -> bool:
    return str(_scalar(value) or "").strip().lower() in {"true","1","yes","y"}


def _text(value) -> str | None:
    v = _scalar(value)
    if v is None:
        return None
    token = str(v).strip()
    return token or None


def _integer(value) -> int | None:
    v = _scalar(value)
    if v is None:
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError, OverflowError):
        return None


def _number(value):
    v = _scalar(value)
    if v is None:
        return None
    try:
        n = float(v)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _statement_key(row: dict, key: str | None) -> str:
    if key:
        return str(key)
    identity = "|".join(str(_scalar(row.get(k)) or "") for k in (
        "exchange", "symbol", "isin", "period_end", "period_kind", "basis", "source_url"
    ))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _company_upsert(cur, rows):
    for row in rows:
        key = company_key(row)
        if not key:
            continue
        cur.execute(
            """
            insert into valueforge.companies(company_key, isin, canonical_name, sector, last_seen_at)
            values (%s,%s,%s,%s,now())
            on conflict (company_key) do update set
              isin=coalesce(excluded.isin, valueforge.companies.isin),
              canonical_name=coalesce(nullif(excluded.canonical_name,''), valueforge.companies.canonical_name),
              sector=coalesce(nullif(excluded.sector,''), valueforge.companies.sector),
              last_seen_at=now()
            """,
            (key, _text(row.get("isin")), _text(row.get("name")), _text(row.get("sector"))),
        )


def _persist_securities(cur, security_master):
    if security_master is None or security_master.empty:
        return 0
    rows = security_master.to_dict("records")
    _company_upsert(cur, rows)
    written = 0
    for row in rows:
        exchange = _text(row.get("exchange"))
        symbol = _text(row.get("symbol"))
        if not exchange or not symbol:
            continue
        cur.execute(
            """
            insert into valueforge.securities(
              exchange,symbol,series,security_code,isin,company_key,
              security_status,master_as_of,source_url,updated_at
            ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
            on conflict (exchange,symbol,series) do update set
              security_code=coalesce(excluded.security_code,valueforge.securities.security_code),
              isin=coalesce(excluded.isin,valueforge.securities.isin),
              company_key=coalesce(excluded.company_key,valueforge.securities.company_key),
              security_status=coalesce(excluded.security_status,valueforge.securities.security_status),
              master_as_of=coalesce(excluded.master_as_of,valueforge.securities.master_as_of),
              source_url=coalesce(excluded.source_url,valueforge.securities.source_url),
              updated_at=now()
            """,
            (
                exchange, symbol, _text(row.get("series")) or "",
                _text(row.get("security_code")), _text(row.get("isin")),
                company_key(row), _text(row.get("security_status")),
                _scalar(row.get("master_as_of")), _text(row.get("master_source")),
            ),
        )
        written += 1
    return written


def _persist_market(cur, market):
    if market is None or market.empty:
        return 0
    rows = market.to_dict("records")
    _company_upsert(cur, rows)
    written = 0
    for row in rows:
        snapshot_date = _scalar(row.get("snapshot_date")) or _scalar(row.get("date"))
        close = _number(row.get("close"))
        exchange, symbol = _text(row.get("exchange")), _text(row.get("symbol"))
        if not snapshot_date or not exchange or not symbol or close is None:
            continue
        cur.execute(
            """
            insert into valueforge.market_prices(
              exchange,symbol,series,snapshot_date,company_key,isin,
              open,high,low,close,volume,turnover,source
            ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            on conflict (exchange,symbol,series,snapshot_date) do update set
              company_key=coalesce(excluded.company_key,valueforge.market_prices.company_key),
              isin=coalesce(excluded.isin,valueforge.market_prices.isin),
              open=coalesce(excluded.open,valueforge.market_prices.open),
              high=coalesce(excluded.high,valueforge.market_prices.high),
              low=coalesce(excluded.low,valueforge.market_prices.low),
              close=excluded.close,
              volume=coalesce(excluded.volume,valueforge.market_prices.volume),
              turnover=coalesce(excluded.turnover,valueforge.market_prices.turnover)
            """,
            (
                exchange, symbol, _text(row.get("series")) or "", snapshot_date,
                company_key(row), _text(row.get("isin")),
                _number(row.get("open")), _number(row.get("high")),
                _number(row.get("low")), close, _number(row.get("volume")),
                _number(row.get("turnover")), "TejHQ EOD bhavcopy",
            ),
        )
        written += 1
    return written


def _persist_filing_registry(cur, registry):
    """Persist both successful and failed filing attempts with parse diagnostics."""
    if registry is None or registry.empty:
        return 0
    rows = registry.to_dict("records")
    _company_upsert(cur, [
        {**row, "name": row.get("company") or row.get("name")}
        for row in rows
    ])
    written = 0
    for row in rows:
        filing_key = _text(row.get("filing_key"))
        source_url = _text(row.get("xbrl_url") or row.get("source_url"))
        if not filing_key or not source_url:
            continue
        parse_status = _text(row.get("parse_status")) or "DISCOVERED"
        parse_error = _text(row.get("parse_error"))
        if parse_error is None and parse_status.startswith("PARSE_FAILED"):
            parse_error = parse_status.partition(":")[2].strip() or parse_status
        basis = "consolidated" if _flag(row.get("consolidated")) else "standalone"
        key = company_key(row)
        if key is None:
            continue
        cur.execute(
            """
            insert into valueforge.filings(
              filing_key,company_key,exchange,symbol,security_code,isin,filing_id,
              period_end,filing_at,reporting_basis,audited,source_url,parser_version,
              parse_status,fact_count,parse_error
            ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            on conflict (filing_key) do update set
              company_key=excluded.company_key, exchange=excluded.exchange,
              symbol=excluded.symbol, security_code=coalesce(excluded.security_code,valueforge.filings.security_code),
              isin=coalesce(excluded.isin,valueforge.filings.isin),
              filing_id=coalesce(excluded.filing_id,valueforge.filings.filing_id),
              period_end=coalesce(excluded.period_end,valueforge.filings.period_end),
              filing_at=coalesce(excluded.filing_at,valueforge.filings.filing_at),
              reporting_basis=excluded.reporting_basis,audited=excluded.audited,
              source_url=excluded.source_url,parser_version=excluded.parser_version,
              parse_status=excluded.parse_status,fact_count=excluded.fact_count,
              parse_error=excluded.parse_error,updated_at=now()
            """,
            (
                filing_key,key,_text(row.get("exchange")),_text(row.get("symbol")),
                _text(row.get("security_code")),_text(row.get("isin")),
                _text(row.get("filing_id")),_scalar(row.get("period_end")),
                _scalar(row.get("filing_ts")),basis,_flag(row.get("audited")),
                source_url,_integer(row.get("parser_version")),parse_status,
                _integer(row.get("fact_count")),parse_error,
            ),
        )
        written += 1
        if parse_error:
            cur.execute(
                """
                insert into valueforge.data_quality_issues(
                  company_key,filing_key,issue_code,severity,detail
                )
                select %s,%s,'XBRL_PARSE_FAILED','ERROR',%s
                where not exists (
                  select 1 from valueforge.data_quality_issues
                  where filing_key=%s and issue_code='XBRL_PARSE_FAILED'
                    and resolved_at is null
                )
                """,
                (key,filing_key,parse_error,filing_key),
            )
    return written


def _record_ingestion(cur, source, status, rows_seen, rows_written, details):
    cur.execute(
        """
        insert into valueforge.ingestion_runs(
          source,started_at,finished_at,status,rows_seen,rows_written,details
        ) values (%s,now(),now(),%s,%s,%s,%s::jsonb)
        """,
        (source,status,int(rows_seen or 0),int(rows_written or 0),_json(details)),
    )


def _persist_statements(cur, fundamentals):
    if fundamentals is None or fundamentals.empty:
        return 0
    rows = fundamentals.to_dict("records")
    _company_upsert(cur, rows)
    written = 0
    metric_fields = {
        "sales","net_profit","profit_before_tax","finance_cost","other_income",
        "operating_profit","ocf","capex","fcf","basic_eps","equity","assets",
        "cash","total_debt","short_debt","long_debt","paid_up_capital",
        "shares_outstanding_cr","shares_outstanding_source","face_value","pe","pb",
        "market_cap_cr","roe","roce","debt_to_equity","interest_coverage",
        "operating_margin","ocf_to_net_profit","sales_cagr_5y","profit_cagr_5y",
        "promoter_holding_pct","promoter_pledge_pct",
    }
    provenance_fields = {
        "matched_fact_tags","diagnostic_fact_names","capex_fact_tags",
        "flow_context_id","instant_context_id","flow_fact_coverage",
        "instant_fact_coverage","unit_currency_note","source_label",
    }
    for row in rows:
        key = company_key(row)
        source_url = _text(row.get("source_url"))
        if not key or not source_url or not _text(row.get("period_end")):
            continue
        filing_key = _statement_key(row, _text(row.get("filing_key")))
        period_end = _scalar(row.get("period_end"))
        period_kind = _text(row.get("period_kind")) or "unknown"
        basis = _text(row.get("basis")) or "unknown"
        filing_id = _text(row.get("filing_id"))
        metrics = {field: _scalar(row.get(field)) for field in metric_fields if field in row}
        provenance = {field: _scalar(row.get(field)) for field in provenance_fields if field in row}
        audited_text = str(_scalar(row.get("audited")) or "").lower()
        audited = audited_text in {"true","1","yes","y"}
        data_quality = _text(row.get("data_quality_status"))
        completeness = _number(row.get("statement_completeness_pct"))
        cur.execute(
            """
            insert into valueforge.filings(
              filing_key,company_key,exchange,symbol,security_code,isin,filing_id,
              period_end,filing_at,reporting_basis,audited,source_url,parser_version,
              parse_status,fact_count
            ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            on conflict (filing_key) do update set
              company_key=excluded.company_key, period_end=excluded.period_end,
              filing_at=coalesce(excluded.filing_at,valueforge.filings.filing_at),
              reporting_basis=excluded.reporting_basis, audited=excluded.audited,
              source_url=excluded.source_url, parse_status=excluded.parse_status,
              fact_count=excluded.fact_count, updated_at=now()
            """,
            (
                filing_key,key,_text(row.get("exchange")),_text(row.get("symbol")),
                _text(row.get("security_code")),_text(row.get("isin")),filing_id,
                period_end,_scalar(row.get("data_as_of")),basis,audited,source_url,
                _integer(row.get("parser_version")),_text(row.get("parse_status")) or "PARSED",
                _integer(row.get("fact_count")),
            ),
        )
        cur.execute(
            """
            insert into valueforge.financial_statements(
              filing_key,company_key,period_end,period_kind,period_days,
              reporting_basis,audited,data_as_of,source_url,taxonomy_family,
              data_quality_status,statement_completeness_pct,metrics,fact_provenance
            ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)
            on conflict (filing_key) do update set
              period_end=excluded.period_end,period_kind=excluded.period_kind,
              period_days=excluded.period_days,reporting_basis=excluded.reporting_basis,
              audited=excluded.audited,data_as_of=excluded.data_as_of,
              source_url=excluded.source_url,taxonomy_family=excluded.taxonomy_family,
              data_quality_status=excluded.data_quality_status,
              statement_completeness_pct=excluded.statement_completeness_pct,
              metrics=excluded.metrics,fact_provenance=excluded.fact_provenance,
              ingested_at=now()
            """,
            (
                filing_key,key,period_end,period_kind,_integer(row.get("period_days")),
                basis,audited,_scalar(row.get("data_as_of")),source_url,
                _text(row.get("taxonomy_family")),data_quality,completeness,
                _json(metrics),_json(provenance),
            ),
        )
        written += 1
    return written


def persist_research_snapshot(market, security_master, fundamentals, ranked, summary, filing_registry=None):
    """Upsert the current data snapshot and research run into private PostgreSQL.

    No connection is attempted unless VALUEFORGE_DATABASE_URL or DATABASE_URL
    is configured. The schema is provisioned separately from database/schema.sql.
    """
    dsn = database_url()
    if not dsn:
        return {"status":"NOT_CONFIGURED","companies":0,"securities":0,"prices":0,"filings":0,"statements":0,"research_rows":0}
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("Database persistence is configured but psycopg is not installed.") from exc

    model_version = os.getenv("VALUEFORGE_MODEL_VERSION","valueforge-0.2.0")
    market_date = _text(summary.get("market_date"))
    counts = {"companies":0,"securities":0,"prices":0,"filings":0,"statements":0,"research_rows":0}
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("select to_regclass('valueforge.companies')")
            if cur.fetchone()[0] is None:
                raise RuntimeError("ValueForge database schema is missing. Apply database/schema.sql before enabling VALUEFORGE_DATABASE_URL.")
            counts["securities"] = _persist_securities(cur,security_master)
            counts["prices"] = _persist_market(cur,market)
            counts["filings"] = _persist_filing_registry(cur,filing_registry)
            counts["statements"] = _persist_statements(cur,fundamentals)
            _record_ingestion(cur,"exchange_security_master","COMPLETED",len(security_master),counts["securities"],{"rows":len(security_master)})
            _record_ingestion(cur,"eod_market_prices","COMPLETED",len(market),counts["prices"],{"rows":len(market)})
            _record_ingestion(cur,"exchange_xbrl_filings","COMPLETED",len(filing_registry) if filing_registry is not None else 0,counts["filings"],{"registry_rows":len(filing_registry) if filing_registry is not None else 0})
            _record_ingestion(cur,"financial_statements","COMPLETED",len(fundamentals),counts["statements"],{"rows":len(fundamentals)})
            cur.execute(
                """
                insert into valueforge.research_runs(market_date,model_version,status,summary)
                values (%s,%s,%s,%s::jsonb) returning id
                """,
                (market_date,model_version,"COMPLETED",_json(summary)),
            )
            run_id = cur.fetchone()[0]
            rows = ranked.to_dict("records") if ranked is not None else []
            for row in rows:
                key = company_key(row)
                exchange = _text(row.get("exchange"))
                if not key or not exchange:
                    continue
                payload_fields = [
                    "isin","sector","period_end","period_kind","basis","source_url",
                    "pe","pb","roe","roce","debt_to_equity","interest_coverage",
                    "operating_margin","ocf_to_net_profit","fcf","sales","net_profit",
                    "total_debt","cash","equity","sales_cagr_5y","profit_cagr_5y",
                    "margin_of_safety_pct","dcf_fair_value_bear","dcf_fair_value_base",
                    "dcf_fair_value_bull","financial_quality_status","financial_quality_issues",
                    "fundamental_match_method",
                ]
                payload = {field:_scalar(row.get(field)) for field in payload_fields if field in row}
                cur.execute(
                    """
                    insert into valueforge.research_results(
                      research_run_id,company_key,exchange,symbol,close,value_score,
                      research_status,financial_quality_status,valuation_status,
                      margin_of_safety_pct,fair_value_bear,fair_value_base,fair_value_bull,payload
                    ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                    on conflict (research_run_id,company_key,exchange) do update set
                      close=excluded.close,value_score=excluded.value_score,
                      research_status=excluded.research_status,
                      financial_quality_status=excluded.financial_quality_status,
                      valuation_status=excluded.valuation_status,
                      margin_of_safety_pct=excluded.margin_of_safety_pct,
                      fair_value_bear=excluded.fair_value_bear,
                      fair_value_base=excluded.fair_value_base,
                      fair_value_bull=excluded.fair_value_bull,payload=excluded.payload
                    """,
                    (
                        run_id,key,exchange,_text(row.get("symbol")),_number(row.get("close")),
                        _number(row.get("value_score")),_text(row.get("research_status")),
                        _text(row.get("financial_quality_status")),_text(row.get("valuation_status")),
                        _number(row.get("margin_of_safety_pct")),_number(row.get("dcf_fair_value_bear")),
                        _number(row.get("dcf_fair_value_base")),_number(row.get("dcf_fair_value_bull")),
                        _json(payload),
                    ),
                )
                counts["research_rows"] += 1
            _record_ingestion(cur,"daily_research_scan","COMPLETED",len(rows),counts["research_rows"],{"research_run_id":run_id,"market_date":market_date})
            counts["companies"] = len({
                company_key(r) for r in (security_master.to_dict("records") if security_master is not None else [])
                if company_key(r)
            })
    return {"status":"CONNECTED","research_run_id":run_id,**counts}
